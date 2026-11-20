"""Select platform for IR Learn."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IREntity

NO_BUTTON = "(无按键)"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([IRTargetSelect(hass.data[DOMAIN][entry.entry_id])])


class IRTargetSelect(IREntity, SelectEntity):
    """Choose which button the next captured code belongs to."""

    _attr_name = "目标按键"
    _attr_icon = "mdi:target"

    def __init__(self, manager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_target"

    @property
    def options(self) -> list[str]:
        return [str(b["name"]) for b in self.manager.buttons] or [NO_BUTTON]

    @property
    def current_option(self) -> str | None:
        for button in self.manager.buttons:
            if button["id"] == self.manager.target_id:
                return str(button["name"])
        return NO_BUTTON

    async def async_select_option(self, option: str) -> None:
        if option != NO_BUTTON:
            await self.manager.async_set_target(option)
