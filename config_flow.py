"""Config flow for MyDeviceForDIY."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    ENTRY_TYPE,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_LISTENER,
)


def _has_listener_entry(hass: HomeAssistant) -> bool:
    return any(
        e.data.get(ENTRY_TYPE) == ENTRY_TYPE_LISTENER
        for e in hass.config_entries.async_entries(DOMAIN)
    )


class MyDeviceForDIYConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Create the UDP listener entry (singleton)."""
        if _has_listener_entry(self.hass):
            return self.async_abort(reason="single_instance")

        if user_input is not None:
            port = int(user_input[CONF_PORT])
            return self.async_create_entry(
                title="MyDeviceForDIY UDP Listener",
                data={
                    ENTRY_TYPE: ENTRY_TYPE_LISTENER,
                    CONF_PORT: port,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_integration_discovery(self, discovery_info) -> FlowResult:
        """Handle discovery of a new device-id via incoming UDP data."""
        device_id = (discovery_info or {}).get(CONF_DEVICE_ID, "")
        device_id = str(device_id).strip()

        if not device_id:
            return self.async_abort(reason="invalid_discovery")

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"device_id": device_id}
        self._discovered_device_id = device_id

        return await self.async_step_confirm_device()

    async def async_step_confirm_device(self, user_input=None) -> FlowResult:
        device_id = getattr(self, "_discovered_device_id", "")

        if user_input is not None:
            name = str(user_input[CONF_DEVICE_NAME]).strip() or device_id
            return self.async_create_entry(
                title=name,
                data={
                    ENTRY_TYPE: ENTRY_TYPE_DEVICE,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: name,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default=device_id): str,
            }
        )
        return self.async_show_form(
            step_id="confirm_device",
            data_schema=schema,
            description_placeholders={"device_id": device_id},
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MyDeviceForDIYOptionsFlowHandler(config_entry)
    
class MyDeviceForDIYOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        # Only the listener entry has options.
        if self.entry.data.get(ENTRY_TYPE) != ENTRY_TYPE_LISTENER:
            return self.async_abort(reason="no_options")

        if user_input is not None:
            return self.async_create_entry(title="", data={CONF_PORT: int(user_input[CONF_PORT])})

        current_port = int(self.entry.options.get(CONF_PORT, self.entry.data.get(CONF_PORT, DEFAULT_PORT)))

        schema = vol.Schema(
            {
                vol.Required(CONF_PORT, default=current_port): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

