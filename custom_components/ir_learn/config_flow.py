"""Config and options flows for IR Learn."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector

from .const import (
    ATTR_NAMES,
    CONF_CODE_SENSOR,
    CONF_ESPHOME_NODE,
    CONF_PROTOCOL,
    DEFAULT_CODE_SENSOR,
    DEFAULT_ESPHOME_NODE,
    DEFAULT_PROTOCOL,
    DOMAIN,
    PROTOCOLS,
)
from .manager import IRButtonManager, parse_names

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ESPHOME_NODE, default=DEFAULT_ESPHOME_NODE): str,
        vol.Required(
            CONF_CODE_SENSOR, default=DEFAULT_CODE_SENSOR
        ): selector.EntitySelector(),
        vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(PROTOCOLS),
    }
)


def _settings_schema(entry: ConfigEntry) -> vol.Schema:
    node = entry.options.get(
        CONF_ESPHOME_NODE, entry.data.get(CONF_ESPHOME_NODE, DEFAULT_ESPHOME_NODE)
    )
    sensor = entry.options.get(
        CONF_CODE_SENSOR, entry.data.get(CONF_CODE_SENSOR, DEFAULT_CODE_SENSOR)
    )
    protocol = entry.options.get(
        CONF_PROTOCOL, entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
    )
    return vol.Schema(
        {
            vol.Required(CONF_ESPHOME_NODE, default=node): str,
            vol.Required(CONF_CODE_SENSOR, default=sensor): selector.EntitySelector(),
            vol.Required(CONF_PROTOCOL, default=protocol): vol.In(PROTOCOLS),
        }
    )


class IRLearnConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IR Learn."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=f"红外学习 · {user_input[CONF_ESPHOME_NODE]}",
                data=user_input,
            )
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IRLearnOptionsFlow()


class IRLearnOptionsFlow(OptionsFlow):
    """Manage buttons and transmitter settings from the UI."""

    def _manager(self) -> IRButtonManager:
        return self.hass.data[DOMAIN][self.config_entry.entry_id]

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_button", "delete_button", "settings"],
        )

    async def async_step_add_button(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            names = parse_names(user_input.get(ATTR_NAMES, ""))
            if not names:
                errors[ATTR_NAMES] = "empty_name"
            elif not await self._manager().async_add_buttons(names):
                errors[ATTR_NAMES] = "exists"
            else:
                return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="add_button",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_NAMES): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_delete_button(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        names = [str(b["name"]) for b in self._manager().buttons]
        if not names:
            return self.async_abort(reason="no_buttons")
        if user_input is not None:
            selected = cv.ensure_list(user_input.get(ATTR_NAMES, []))
            if not await self._manager().async_delete_buttons(selected):
                return self.async_abort(reason="not_found")
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="delete_button",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_NAMES): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=names, multiple=True)
                    )
                }
            ),
        )

    async def async_step_settings(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=user_input
            )
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="settings", data_schema=_settings_schema(self.config_entry)
        )
