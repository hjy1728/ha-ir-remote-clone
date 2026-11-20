"""Shared entity base for IR Learn."""

from __future__ import annotations

from .manager import IRButtonManager


class IREntity:
    """Common device/listener wiring for all IR Learn entities."""

    _attr_has_entity_name = True

    def __init__(self, manager: IRButtonManager) -> None:
        self.manager = manager
        self._attr_device_info = manager.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.manager.async_add_listener(self.async_write_ha_state)
        )
