"""Actions for the IR Learn integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CODE,
    ATTR_NAME,
    ATTR_NAMES,
    ATTR_PULSES,
    ATTR_REPEATS,
    DOMAIN,
    SERVICE_ADD_BUTTON,
    SERVICE_CLEAR_BUFFER,
    SERVICE_DELETE_BUTTON,
    SERVICE_RECEIVE_CODE,
    SERVICE_SEND_BUTTON,
)
from .manager import IRButtonManager

ATTR_CONFIG_ENTRY_ID = "config_entry_id"


def _require_names(data: dict) -> dict:
    if not data.get(ATTR_NAME) and not data.get(ATTR_NAMES):
        raise vol.Invalid("必须提供 name 或 names")
    return data


_BUTTON_NAMES_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_NAMES): vol.All(cv.ensure_list, [cv.string]),
    }
)
ADD_BUTTON_SCHEMA = vol.Schema(vol.All(_BUTTON_NAMES_SCHEMA, _require_names))
DELETE_BUTTON_SCHEMA = ADD_BUTTON_SCHEMA
SEND_BUTTON_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_NAME): cv.string,
    }
)
CLEAR_BUFFER_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})
RECEIVE_CODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CODE): cv.string,
        vol.Optional(ATTR_REPEATS): cv.positive_int,
        vol.Optional(ATTR_PULSES): cv.positive_int,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    }
)

SERVICES = (
    SERVICE_ADD_BUTTON,
    SERVICE_DELETE_BUTTON,
    SERVICE_SEND_BUTTON,
    SERVICE_CLEAR_BUFFER,
    SERVICE_RECEIVE_CODE,
)


def _names_from_call(call: ServiceCall) -> list[str]:
    """Return names from either the legacy ``name`` or the new ``names`` field."""
    names = list(call.data.get(ATTR_NAMES, []))
    name = call.data.get(ATTR_NAME)
    if name:
        names.append(name)
    return names


def _get_manager(hass: HomeAssistant, call: ServiceCall) -> IRButtonManager:
    managers = hass.data.get(DOMAIN, {})
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    manager = managers.get(entry_id) if entry_id else next(iter(managers.values()), None)
    if manager is None:
        raise HomeAssistantError("未找到已加载的红外学习按键集成")
    return manager


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration actions once."""

    async def async_add_button(call: ServiceCall) -> None:
        manager = _get_manager(hass, call)
        if not await manager.async_add_buttons(_names_from_call(call)):
            raise HomeAssistantError("按键名称为空或已存在")

    async def async_delete_button(call: ServiceCall) -> None:
        manager = _get_manager(hass, call)
        if not await manager.async_delete_buttons(_names_from_call(call)):
            raise HomeAssistantError("按键不存在")

    async def async_send_button(call: ServiceCall) -> None:
        manager = _get_manager(hass, call)
        if not await manager.async_send(call.data[ATTR_NAME]):
            raise HomeAssistantError("按键不存在或尚未学习红外码")

    async def async_clear_buffer(call: ServiceCall) -> None:
        await _get_manager(hass, call).async_clear_buffer()

    async def async_receive_code(call: ServiceCall) -> None:
        _get_manager(hass, call).async_receive_code(
            call.data[ATTR_CODE],
            call.data.get(ATTR_REPEATS),
            call.data.get(ATTR_PULSES),
        )

    hass.services.async_register(
        DOMAIN, SERVICE_RECEIVE_CODE, async_receive_code, schema=RECEIVE_CODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_BUTTON, async_add_button, schema=ADD_BUTTON_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_BUTTON,
        async_delete_button,
        schema=DELETE_BUTTON_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_BUTTON, async_send_button, schema=SEND_BUTTON_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_BUFFER, async_clear_buffer, schema=CLEAR_BUFFER_SCHEMA
    )


@callback
def async_remove_services(hass: HomeAssistant) -> None:
    """Remove the integration actions when the last entry unloads."""
    for service in SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
