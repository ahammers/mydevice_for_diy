"""MyDevice for DIY integration.

This integration provides a simple *push* interface for DIY devices:

- Home Assistant listens on a TCP port (default: 55355).
- Devices connect and send JSON objects.
- For robustness with TCP streams, the protocol is **NDJSON**:
  one JSON object per line (newline-delimited JSON).

Packet format (one line):

    {"device":"ABC123","type":"ht","data":{"t":21.3,"h":45.6}}

Behavior:
- Unknown device_id -> triggers a discovery flow (shows as "Discovered").
- Configured device_id -> updates entities immediately.

Currently supported device type:
- "ht": humidity ("h" in %) and temperature ("t" in degC)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_LISTENER,
    SIGNAL_DATA_RECEIVED,
    SUPPORTED_DEVICE_TYPES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


def _data_signal(device_id: str) -> str:
    """Create the dispatcher signal name for a device."""
    return f"{SIGNAL_DATA_RECEIVED}_{device_id}"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Initialize the integration's global data container."""
    hass.data.setdefault(
        DOMAIN,
        {
            "server": None,               # asyncio.Server
            "port": DEFAULT_PORT,         # configured listen port
            "values": {},                 # device_id -> dict("t"/"h" -> float)
            "device_types": {},           # device_id -> type string
            "configured": set(),          # configured device_ids
            "discovery_started": set(),   # device_ids for which we already started discovery
        },
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    entry_type = entry.data.get(CONF_ENTRY_TYPE)

    if entry_type == ENTRY_TYPE_LISTENER:
        port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
        hass.data[DOMAIN]["port"] = port
        await _ensure_server_started(hass, port)
        return True

    if entry_type == ENTRY_TYPE_DEVICE:
        device_id = str(entry.data[CONF_DEVICE_ID])
        device_type = str(entry.data[CONF_DEVICE_TYPE])

        hass.data[DOMAIN]["configured"].add(device_id)
        hass.data[DOMAIN]["device_types"][device_id] = device_type

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    _LOGGER.error("Unknown entry type: %s", entry_type)
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_type = entry.data.get(CONF_ENTRY_TYPE)

    if entry_type == ENTRY_TYPE_DEVICE:
        device_id = str(entry.data.get(CONF_DEVICE_ID, ""))
        ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if ok and device_id:
            hass.data[DOMAIN]["configured"].discard(device_id)
        return ok

    if entry_type == ENTRY_TYPE_LISTENER:
        await _stop_server(hass)
        return True

    return False


async def _ensure_server_started(hass: HomeAssistant, port: int) -> None:
    """Start the TCP server if it isn't running yet."""
    if hass.data[DOMAIN].get("server") is not None:
        return

    async def _client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break  # client closed

                raw = line.strip()
                if not raw:
                    continue

                try:
                    obj = json.loads(raw.decode("utf-8"))
                except Exception:
                    _LOGGER.warning("Invalid JSON from %s: %r", peer, raw[:200])
                    continue

                await _handle_packet(hass, obj)
        except Exception as ex:
            # Debug level: network interruptions happen.
            _LOGGER.debug("Client error from %s: %s", peer, ex)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(_client_connected, host="0.0.0.0", port=port)
    hass.data[DOMAIN]["server"] = server
    _LOGGER.info("MyDevice for DIY listening on TCP port %s", port)


async def _stop_server(hass: HomeAssistant) -> None:
    """Stop the TCP server."""
    server: asyncio.Server | None = hass.data[DOMAIN].get("server")
    if server is None:
        return

    server.close()
    await server.wait_closed()
    hass.data[DOMAIN]["server"] = None
    _LOGGER.info("MyDevice for DIY server stopped")


async def _handle_packet(hass: HomeAssistant, obj: Any) -> None:
    """Validate and process a single packet."""
    if not isinstance(obj, dict):
        return

    device_id = obj.get("device")
    device_type = obj.get("type")
    data = obj.get("data")

    if not isinstance(device_id, str) or not device_id:
        _LOGGER.warning("Missing device id")
        return
    if not isinstance(device_type, str) or device_type not in SUPPORTED_DEVICE_TYPES:
        _LOGGER.warning("Unsupported device type %s", device_type)
        return
    if not isinstance(data, dict):
        _LOGGER.warning("Missing device data")
        return

    # Store the last values we received.
    values = hass.data[DOMAIN]["values"].setdefault(device_id, {})
    hass.data[DOMAIN]["device_types"][device_id] = device_type

    if device_type == "ht":
        if "t" in data:
            try:
                values["t"] = float(data["t"])
            except Exception:
                pass
        if "h" in data:
            try:
                values["h"] = float(data["h"])
            except Exception:
                pass

    _LOGGER.warning("Received valid data from %s: %s", device_id, values)

    # Unknown device? Trigger discovery once so it appears under "Discovered".
    if device_id not in hass.data[DOMAIN]["configured"]:
        _LOGGER.warning("A")
        if device_id not in hass.data[DOMAIN]["discovery_started"]:
            _LOGGER.warning("B")
            hass.data[DOMAIN]["discovery_started"].add(device_id)
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
                    data={CONF_DEVICE_ID: device_id, CONF_DEVICE_TYPE: device_type},
                )
            )
        _LOGGER.warning("C")
        return
    _LOGGER.warning("D")

    # Configured device -> tell the entities to update.
    async_dispatcher_send(hass, _data_signal(device_id))
