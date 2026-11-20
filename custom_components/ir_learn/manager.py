"""Runtime manager for the IR Learn integration."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:  # HA < 2022.6
    from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import (
    CONF_CODE_SENSOR,
    CONF_ESPHOME_NODE,
    CONF_PROTOCOL,
    DEFAULT_CODE_SENSOR,
    DEFAULT_ESPHOME_NODE,
    DEFAULT_PROTOCOL,
    DOMAIN,
    IGNORED_STATES,
    MIN_RAW_VALUES,
    PROTOCOL_NEC,
    PROTOCOL_PRONTO,
    PROTOCOL_RAW,
    SERVICE_SEND_NEC,
    SERVICE_SEND_PRONTO,
    SERVICE_SEND_RAW,
    STORAGE_KEY,
    STORAGE_VERSION,
)

DEFAULT_REPEATS = 2
MIN_PRONTO_PAIRS = 10


def _parse_summary(state: str) -> tuple[int, int, str]:
    """Parse the ESPHome state prefix like ``脉冲18 × 7帧 | <pronto>``.

    Returns (repeats, pulses, pure_code). Defaults are used when absent so
    older firmware states keep working.
    """
    repeats, pulses = DEFAULT_REPEATS, 0
    match = re.match(r"^脉冲(\d+)\s*×\s*(\d+)帧\s*\|\s*(.*)$", state)
    if match:
        pulses = int(match.group(1))
        repeats = max(1, int(match.group(2)) - 1)
        state = match.group(3).strip()
    # text_sensor 发的是裸 pronto（无协议前缀）。补回前缀，否则
    # _is_valid_code 会当 raw 逗号分割，判定无效导致学习失败。
    if re.match(r"^0000\s+[0-9A-Fa-f]{4}\s+[0-9A-Fa-f]{4}\s+", state):
        return repeats, pulses, "pronto:" + state
    return repeats, pulses, state


def _pronto_pulse_count(code: str) -> int:
    """Size of the pronto data area in bytes.

    The 3rd header word is the number of duration pairs. Each pair is two
    16-bit words (mark + space) = 4 bytes.
    """
    payload = code.split(":", 1)[-1].strip()
    words = payload.split()
    if len(words) >= 4 and words[0].lower() == "0000":
        try:
            return int(words[2], 16) * 4
        except ValueError:
            return 0
    return 0


def _parse_ir_code(code: str, fallback_protocol: str) -> tuple[str, str]:
    """Return (protocol, payload) decoded from an optional ``prefix:`` code."""
    stripped = code.strip()
    lowered = stripped.lower()
    for prefix, protocol in (
        ("nec:", PROTOCOL_NEC),
        ("raw:", PROTOCOL_RAW),
        ("pronto:", PROTOCOL_PRONTO),
    ):
        if lowered.startswith(prefix):
            return protocol, stripped[len(prefix) :].strip()
    return fallback_protocol, stripped


def _raw_to_pronto(code: str) -> str:
    """Convert a raw microsecond timing list to a standard Pronto hex string.

    Remote controls repeat the same frame several times per button press.
    ESP32 RMT buffers can only send one frame, so keep only the first frame.
    """
    try:
        vals = [int(p.strip()) for p in code.split(",") if p.strip()]
    except ValueError:
        return code
    if not vals:
        return code

    # 去掉结尾超长静默（如 -25000 / 25000）
    if abs(vals[-1]) > 10000:
        vals = vals[:-1]

    # 找重复帧边界：一个长 space（<-5000us）后跟一个引导正脉冲（>1500us）。
    # 第一段（含其引导）就是完整单帧。
    cut = len(vals)
    for i in range(1, len(vals) - 1):
        if vals[i] < -5000 and 1500 < vals[i + 1] < 6000:
            cut = i + 1
            break
    frame = vals[:cut]

    # 38kHz carrier: one pronto word ≈ 26 us (freq word 0x006D)
    freq_word = 0x006D
    unit = 26.0
    words = [max(1, int(round(abs(v) / unit))) for v in frame]
    # Pronto 要求 mark/space 成对，word 数必须为偶数，否则
    # ESPHome 报 "Inconsistent data, not sending"。
    if len(words) % 2:
        words = words[:-1]
    header = [0x0000, freq_word, len(words) // 2, 0x0000]
    return " ".join(f"{w:04X}" for w in header + words)


class IRButtonManager:
    """Hold learned buttons and bridge the ESPHome receiver/transmitter."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self.buttons: list[dict[str, Any]] = []
        self.buffer = ""
        self.buffer_repeats: int = DEFAULT_REPEATS
        self.buffer_pulses: int = 0
        self.last_code = ""
        self.last_repeats: int = DEFAULT_REPEATS
        self.last_pulses: int = 0
        self.last_save: str = ""
        self.target_id: str | None = None
        self.learning = False
        self._listeners: list[Callable[[], None]] = []
        self._new_button_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._unsub_state: Callable[[], None] | None = None
        self._last_seen_code = ""
        self._last_seen_ts = 0.0

    @property
    def node(self) -> str:
        raw = str(
            self.entry.options.get(
                CONF_ESPHOME_NODE,
                self.entry.data.get(CONF_ESPHOME_NODE, DEFAULT_ESPHOME_NODE),
            )
        )
        return slugify(raw)

    @property
    def code_sensor(self) -> str:
        return str(
            self.entry.options.get(
                CONF_CODE_SENSOR,
                self.entry.data.get(CONF_CODE_SENSOR, DEFAULT_CODE_SENSOR),
            )
        )

    @property
    def protocol(self) -> str:
        return str(
            self.entry.options.get(
                CONF_PROTOCOL,
                self.entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
            )
        )

    @property
    def buffer_protocol(self) -> str:
        return _parse_ir_code(self.buffer, self.protocol)[0]

    @property
    def target_name(self) -> str:
        for button in self.buttons:
            if button["id"] == self.target_id:
                return str(button["name"])
        return "(无按键)"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="红外学习按键",
            manufacturer="ESPHome + Home Assistant",
            model=self.protocol.upper(),
        )

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.buttons = list(data.get("buttons", []))
        self.buffer = str(data.get("buffer", ""))
        self.buffer_repeats = int(data.get("buffer_repeats", DEFAULT_REPEATS))
        self.buffer_pulses = int(data.get("buffer_pulses", 0))
        self.target_id = data.get("target_id")
        if self.buttons and not any(b["id"] == self.target_id for b in self.buttons):
            self.target_id = self.buttons[0]["id"]

    def async_start(self) -> None:
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.code_sensor], self._handle_state_change
        )
        current = self.hass.states.get(self.code_sensor)
        _LOGGER.warning(
            "IR_DEBUG 监听实体=%s 当前状态=%s",
            self.code_sensor,
            current.state if current else "不存在",
        )

    def async_stop(self) -> None:
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def register_new_button_callback(
        self, callback_: Callable[[dict[str, Any]], None]
    ) -> None:
        self._new_button_callbacks.append(callback_)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def _async_persist(self) -> None:
        await self._store.async_save(
            {
                "buttons": self.buttons,
                "buffer": self.buffer,
                "buffer_repeats": self.buffer_repeats,
                "buffer_pulses": self.buffer_pulses,
                "target_id": self.target_id,
            }
        )
        self._notify()

    @staticmethod
    def _is_valid_code(code: str) -> bool:
        lowered = code.lower()
        if lowered.startswith("pronto:"):
            # pronto header 第3个 word 是时长对数。引导头被切成独立脉冲时
            # 只有 1~2 对（4~8 字节），必须拒绝，否则碎片会覆盖完整码。
            words = code[7:].strip().split()
            if len(words) < 4 or words[0].lower() != "0000":
                return False
            try:
                return int(words[2], 16) >= MIN_PRONTO_PAIRS
            except ValueError:
                return False
        if lowered.startswith("nec:"):
            return True
        payload = code[4:].strip() if lowered.startswith("raw:") else code
        parts = [p for p in payload.split(",") if p.strip()]
        return len(parts) >= MIN_RAW_VALUES

    @callback
    def _handle_state_change(self, event: Any) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        code = str(new_state.state or "").strip()
        if code.lower() in IGNORED_STATES or code.startswith("等待"):
            return
        repeats, pulses, code = _parse_summary(code)
        # 碎片（引导头被单独切开）直接丢弃，不覆盖显示也不触发学习
        if not self._is_valid_code(code):
            return
        # 字节数统一由 pronto header 计算
        pulses = _pronto_pulse_count(code) or pulses
        now = time.monotonic()
        if code == self._last_seen_code and now - self._last_seen_ts < 0.6:
            return
        _LOGGER.warning(
            "IR_DEBUG 收到状态变化 code=%s 字节=%d 学习模式=%s",
            code[:60], pulses, self.learning,
        )
        self._last_seen_code = code
        self._last_seen_ts = now
        self.last_code = code
        self.last_repeats = repeats
        self.last_pulses = pulses
        if self.learning:
            if not self._is_valid_code(code):
                self._notify()
                return
            self.learning = False
            self.buffer = code
            self.buffer_repeats = repeats
            self.buffer_pulses = pulses
            self._notify()
            self.hass.async_create_task(self._async_persist())
        else:
            self._notify()

    @callback
    def async_receive_code(
        self, code: str, repeats: int | None = None, pulses: int | None = None
    ) -> None:
        """Handle a code pushed directly from ESPHome (avoids 255-char state limit)."""
        code = str(code or "").strip()
        if not code or code.lower() in IGNORED_STATES or code.startswith("等待"):
            return
        parsed_repeats, parsed_pulses, code = _parse_summary(code)
        # 碎片直接丢弃，不覆盖显示也不触发学习
        if not self._is_valid_code(code):
            return
        if repeats is not None:
            parsed_repeats = int(repeats)
        # 字节数统一由 pronto header 计算，忽略 ESPHome 推来的脉冲对数
        parsed_pulses = _pronto_pulse_count(code) or parsed_pulses
        now = time.monotonic()
        # 用独立 key 去重，避免被 text_sensor 状态变化先一步挡掉
        push_key = "push:" + code
        if push_key == self._last_seen_code and now - self._last_seen_ts < 0.6:
            return
        self._last_seen_code = push_key
        self._last_seen_ts = now
        self.last_code = code
        self.last_repeats = parsed_repeats
        self.last_pulses = parsed_pulses
        _LOGGER.warning(
            "IR_DEBUG 收到推送码 len=%d 重复=%d 字节=%d 学习模式=%s",
            len(code), parsed_repeats, parsed_pulses, self.learning,
        )
        if self.learning:
            if not self._is_valid_code(code):
                self._notify()
                return
            self.learning = False
            self.buffer = code
            self.buffer_repeats = parsed_repeats
            self.buffer_pulses = parsed_pulses
            self._notify()
            self.hass.async_create_task(self._async_persist())
        else:
            self._notify()

    @callback
    def async_set_learning(self, value: bool) -> None:
        self.learning = value
        if value:
            self.buffer = ""
        self._notify()
        self.hass.async_create_task(self._async_persist())

    async def async_add_button(self, name: str) -> bool:
        name = name.strip()
        if not name or any(b["name"] == name for b in self.buttons):
            return False
        button: dict[str, Any] = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "code": "",
        }
        self.buttons.append(button)
        self.target_id = button["id"]
        self.buffer = ""
        await self._async_persist()
        for add in list(self._new_button_callbacks):
            add(button)
        return True

    async def async_delete_button(self, name: str) -> bool:
        before = len(self.buttons)
        self.buttons = [b for b in self.buttons if b["name"] != name]
        if len(self.buttons) == before:
            return False
        if not any(b["id"] == self.target_id for b in self.buttons):
            self.target_id = self.buttons[0]["id"] if self.buttons else None
        await self._async_persist()
        return True

    async def async_set_target(self, name: str) -> bool:
        for button in self.buttons:
            if button["name"] == name:
                self.target_id = button["id"]
                await self._async_persist()
                return True
        return False

    async def async_save_buffer(self) -> bool:
        if not self.buffer:
            return False
        for button in self.buttons:
            if button["id"] == self.target_id:
                protocol, payload = _parse_ir_code(self.buffer, self.protocol)
                # raw 码转成标准 pronto 保存：pronto 更紧凑，发射更可靠，
                # 不受 ESP32 RMT 缓冲限制（raw 长码发不出去）。
                if protocol == PROTOCOL_RAW:
                    payload = _raw_to_pronto(payload)
                    protocol = PROTOCOL_PRONTO
                button["code"] = payload
                button["protocol"] = protocol
                button["repeat"] = self.buffer_repeats
                button["pulses"] = self.buffer_pulses
                count = len(payload.split())
                self.last_save = (
                    f"已保存 {button['name']} · {protocol} · 字节{self.buffer_pulses} "
                    f"× 重复{self.buffer_repeats} · {count} words"
                )
                await self._async_persist()
                return True
        return False

    async def async_clear_buffer(self) -> None:
        self.buffer = ""
        await self._async_persist()

    def get_button(self, name_or_id: str) -> dict[str, Any] | None:
        for button in self.buttons:
            if button["name"] == name_or_id or button["id"] == name_or_id:
                return button
        return None

    async def async_send(self, name_or_id: str) -> bool:
        button = self.get_button(name_or_id)
        if button is None or not button.get("code"):
            return False
        code = str(button["code"])
        protocol = str(button.get("protocol", self.protocol))
        if protocol == PROTOCOL_NEC:
            try:
                address_text, command_text = [p.strip() for p in code.split(",", 1)]
                data: dict[str, Any] = {
                    "address": int(address_text, 0),
                    "command": int(command_text, 0),
                }
            except (ValueError, IndexError):
                return False
            service = SERVICE_SEND_NEC
        elif protocol == PROTOCOL_PRONTO:
            data = {
                "code_str": code,
                "repeats": int(button.get("repeat", DEFAULT_REPEATS)),
            }
            service = SERVICE_SEND_PRONTO
        else:
            data = {"code_str": code}
            service = SERVICE_SEND_RAW
        full_service = f"{self.node}_{service}"
        exists = self.hass.services.has_service("esphome", full_service)
        _LOGGER.warning(
            "IR_DEBUG 发送 按键=%s 协议=%s 重复=%s 服务=esphome.%s 存在=%s 码长=%d",
            name_or_id,
            protocol,
            data.get("repeats", "-"),
            full_service,
            exists,
            len(data.get("code_str", code)),
        )
        await self.hass.services.async_call(
            "esphome", full_service, data, blocking=False
        )
        return True
