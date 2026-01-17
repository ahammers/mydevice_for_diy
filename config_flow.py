"""Config flow for MyDevice for DIY.

We use two kinds of entries:
- Listener entry (singleton): configures the TCP port and starts the server.
- Device entry: created via discovery when a new device sends data.

The discovery source is integration_discovery so devices show up under "Discovered".
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_LISTENER,
    SUPPORTED_DEVICE_TYPES,
)


class MyDeviceForDiyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration for MyDevice for DIY."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: dict | None = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Create the listener entry."""
        # Allow only a single listener configuration.
        if any(e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_LISTENER for e in self._async_current_entries()):
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            port = int(user_input[CONF_PORT])
            return self.async_create_entry(
                title="MyDevice for DIY Listener",
                data={CONF_ENTRY_TYPE: ENTRY_TYPE_LISTENER, CONF_PORT: port},
            )

        schema = vol.Schema({vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int)})
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_integration_discovery(self, discovery_info=None, user_input=None) -> FlowResult:
        """Handle discovery triggered by the TCP server."""
        # First call: store discovery payload
        if discovery_info is not None:
            self._discovery_info = discovery_info

        if self._discovery_info is None:
            return self.async_abort(reason="no_discovery_info")

        device_id = str(self._discovery_info.get(CONF_DEVICE_ID, "")).strip()
        device_type = str(self._discovery_info.get(CONF_DEVICE_TYPE, "")).strip()

        if not device_id or device_type not in SUPPORTED_DEVICE_TYPES:
            return self.async_abort(reason="not_supported")

        # One config entry per device_id.
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"device": device_id}

        # If the listener is missing, discovery is not useful yet.
        if not any(e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_LISTENER for e in self._async_current_entries()):
            return self.async_abort(reason="listener_missing")

        # Second call: user submitted the form
        if user_input is not None:
            name = str(user_input.get(CONF_NAME, "")).strip() or device_id
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ENTRY_TYPE: ENTRY_TYPE_DEVICE,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_TYPE: device_type,
                    CONF_NAME: name,
                },
            )

        schema = vol.Schema({vol.Required(CONF_NAME, default=device_id): str})
        return self.async_show_form(step_id="integration_discovery", data_schema=schema)

    @callback
    def async_get_options_flow(self, config_entry):
        return MyDeviceForDiyOptionsFlow(config_entry)


class MyDeviceForDiyOptionsFlow(config_entries.OptionsFlow):
    """Options flow (currently only the friendly name)."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if self.entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_DEVICE:
            return self.async_abort(reason="not_supported")

        if user_input is not None:
            return self.async_create_entry(title="", data={CONF_NAME: str(user_input[CONF_NAME])})

        current_name = self.entry.options.get(CONF_NAME, self.entry.data.get(CONF_NAME, self.entry.title))
        schema = vol.Schema({vol.Required(CONF_NAME, default=current_name): str})
        return self.async_show_form(step_id="init", data_schema=schema)
