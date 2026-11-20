"""Sensor platform for IR Learn."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IREntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([IRLastCodeSensor(hass.data[DOMAIN][entry.entry_id])])


class IRLastCodeSensor(IREntity, SensorEntity):
    """Show the most recent captured IR code and learning state."""

    _attr_name = "最近红外码"
    _attr_icon = "mdi:barcode"
    _attr_should_poll = False

    def __init__(self, manager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_last_code"

    @property
    def native_value(self) -> str:
        code = self.manager.last_code
        if not code:
            return "等待按键…"
        size = self.manager.last_pulses
        frames = self.manager.last_repeats
        return f"字节{size} · {frames}帧"

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "最近完整码": self.manager.last_code,
            "最近字节数": self.manager.last_pulses,
            "最近重复次数": self.manager.last_repeats,
            "最近保存结果": self.manager.last_save,
            "暂存码": self.manager.buffer,
            "暂存协议": self.manager.buffer_protocol if self.manager.buffer else "",
            "暂存字节数": self.manager.buffer_pulses,
            "暂存重复次数": self.manager.buffer_repeats,
            "目标按键": self.manager.target_name,
            "学习模式": self.manager.learning,
            "最近码有效": (
                self.manager._is_valid_code(self.manager.last_code)
                if self.manager.last_code
                else False
            ),
            "协议": self.manager.protocol,
            "按键列表": [
                {
                    "名称": b["name"],
                    "已学习": bool(b["code"]),
                    "协议": b.get("protocol", self.manager.protocol),
                    "字节": b.get("pulses", 0),
                    "重复": b.get("repeat", 0),
                }
                for b in self.manager.buttons
            ],
        }
