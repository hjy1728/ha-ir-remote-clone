"""Switch platform for IR Learn."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import IREntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([IRLearningSwitch(hass.data[DOMAIN][entry.entry_id])])


class IRLearningSwitch(IREntity, SwitchEntity):
    """Turn on to capture the next IR code."""

    _attr_name = "学习模式"
    _attr_icon = "mdi:record-rec"

    def __init__(self, manager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_learning"

    @property
    def is_on(self) -> bool:
        return self.manager.learning

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.manager.async_set_learning(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.manager.async_set_learning(False)
        self.async_write_ha_state()
