"""Button platform for IR Learn."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IREntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [IRSaveButton(manager), IRClearButton(manager)]
        + [IRSendButton(manager, button) for button in manager.buttons]
    )

    @callback
    def _add_new_button(button: dict) -> None:
        async_add_entities([IRSendButton(manager, button)])

    manager.register_new_button_callback(_add_new_button)


class IRSaveButton(IREntity, ButtonEntity):
    """Save the captured code into the selected target button."""

    _attr_name = "保存当前码到目标按键"
    _attr_icon = "mdi:content-save-check"

    def __init__(self, manager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_save"

    @property
    def available(self) -> bool:
        return bool(self.manager.buffer and self.manager.target_id)

    async def async_press(self) -> None:
        if not await self.manager.async_save_buffer():
            raise HomeAssistantError("没有暂存码，或未选择目标按键")
        self.async_write_ha_state()


class IRClearButton(IREntity, ButtonEntity):
    """Discard the captured code."""

    _attr_name = "清空暂存码"
    _attr_icon = "mdi:eraser"

    def __init__(self, manager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_clear"

    @property
    def available(self) -> bool:
        return bool(self.manager.buffer)

    async def async_press(self) -> None:
        await self.manager.async_clear_buffer()
        self.async_write_ha_state()


class IRSendButton(IREntity, ButtonEntity):
    """One dashboard button per learned key."""

    _attr_icon = "mdi:remote"

    def __init__(self, manager, button: dict) -> None:
        super().__init__(manager)
        self._button = button
        self._attr_name = f"发送-{button['name']}"
        self._attr_unique_id = f"{manager.entry.entry_id}_send_{button['id']}"

    @property
    def available(self) -> bool:
        return bool(self._button.get("code"))

    async def async_press(self) -> None:
        await self.manager.async_send(self._button["name"])

    @callback
    def _handle_update(self) -> None:
        current = next(
            (b for b in self.manager.buttons if b["id"] == self._button["id"]),
            None,
        )
        if current is None:
            self.hass.async_create_task(self.async_remove())
            return
        self._button = current
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.async_add_listener(self._handle_update))
