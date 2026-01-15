"""Eigene MyDeviceForDIY integration.

- One "listener" config entry opens the UDP port and receives data.
- Each thermometer is added as a separate "device" config entry (created via discovery)
  and exposes temperature/humidity sensor entities.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    ENTRY_TYPE,
    ENTRY_TYPE_DEVICE,
    ENTRY_TYPE_LISTENER,
    SIGNAL_DEVICE_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]


@dataclass
class DeviceState:
    """Latest known state for one thermometer."""

    device_id: str
    last_update_utc: int | None = None  # measurement timestamp (UTC seconds)
    temperature_c: float | None = None
    humidity_percent: float | None = None
    last_seen_utc: int | None = None  # receive time


class _UdpServer(asyncio.DatagramProtocol):
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        sockname = getattr(transport, "get_extra_info", lambda *_: None)("sockname")
        _LOGGER.info("UDP listener started on %s", sockname)

    def connection_lost(self, exc: Exception | None) -> None:
        _LOGGER.info("UDP listener stopped (%s)", exc)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            text = data.decode("utf-8", errors="replace").strip()
        except Exception:  # pragma: no cover
            _LOGGER.debug("Failed to decode datagram from %s", addr)
            return

        now = int(time.time())

        # ACK immediately with *current* timestamp
        try:
            if self.transport is not None:
                self.transport.sendto(f"{now};1".encode("utf-8"), addr)
        except Exception:  # pragma: no cover
            _LOGGER.debug("Failed to send ACK to %s", addr)

        # Parse payload (best effort)
        # Format: <utc-ts>;<record-type>;<device-id>;<temp*10>;<hum*10>
        parts = text.split(";")
        if len(parts) < 3:
            _LOGGER.debug("Ignoring short datagram from %s: %r", addr, text)
            return

        raw_ts = parts[0].strip()
        raw_type = parts[1].strip()
        device_id = parts[2].strip()

        if not device_id:
            _LOGGER.debug("Ignoring datagram with empty device-id from %s: %r", addr, text)
            return

        # Only handle record type 11 (ht) for now; ignore others silently
        if raw_type not in ("11", "ht", "HT"):
            _LOGGER.debug("Ignoring record-type %r from %s: %r", raw_type, addr, text)
            return

        meas_ts = now
        if raw_ts != "":
            try:
                ts_val = int(raw_ts)
                # negative = relative age in seconds (e.g. -40 => 40 seconds old)
                meas_ts = now + ts_val if ts_val < 0 else ts_val
            except ValueError:
                # keep now
                pass

        temp_c: float | None = None
        hum_p: float | None = None

        if len(parts) >= 4 and parts[3].strip() != "":
            try:
                temp_c = int(parts[3].strip()) / 10.0
            except ValueError:
                pass

        if len(parts) >= 5 and parts[4].strip() != "":
            try:
                hum_p = int(parts[4].strip()) / 10.0
            except ValueError:
                pass

        store: dict[str, DeviceState] = self.hass.data[DOMAIN]["devices"]

        st = store.get(device_id)
        if st is None:
            st = DeviceState(device_id=device_id)
            store[device_id] = st
            _maybe_trigger_discovery(self.hass, device_id)

        st.last_seen_utc = now
        st.last_update_utc = meas_ts
        if temp_c is not None:
            st.temperature_c = temp_c
        if hum_p is not None:
            st.humidity_percent = hum_p

        async_dispatcher_send(self.hass, SIGNAL_DEVICE_UPDATED, device_id)


def _maybe_trigger_discovery(hass: HomeAssistant, device_id: str) -> None:
    """Trigger a discovery flow for unknown devices."""
    # If the device is already configured (config entry exists), do nothing.
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(ENTRY_TYPE) == ENTRY_TYPE_DEVICE and entry.data.get(CONF_DEVICE_ID) == device_id:
            return

    from homeassistant import config_entries

    _LOGGER.info("Discovered new thermometer %s (starting discovery flow)", device_id)

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_DEVICE_ID: device_id},
        )
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration from YAML (not supported)."""
    hass.data.setdefault(DOMAIN, {"devices": {}, "server": None, "port": None})
    return True


async def _start_listener(hass: HomeAssistant, port: int) -> None:
    """Start UDP listener (if not already running)."""
    server = hass.data[DOMAIN].get("server")
    if server is not None and hass.data[DOMAIN].get("port") == port:
        return

    # Stop existing server if port changes
    await _stop_listener(hass)

    loop = asyncio.get_running_loop()
    protocol = _UdpServer(hass)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=("0.0.0.0", port),
    )

    hass.data[DOMAIN]["server"] = (transport, protocol)
    hass.data[DOMAIN]["port"] = port


async def _stop_listener(hass: HomeAssistant) -> None:
    """Stop UDP listener if running."""
    server = hass.data[DOMAIN].get("server")
    if server is None:
        return
    transport, _protocol = server
    try:
        transport.close()
    except Exception:  # pragma: no cover
        pass
    hass.data[DOMAIN]["server"] = None
    hass.data[DOMAIN]["port"] = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {"devices": {}, "server": None, "port": None})

    entry_type = entry.data.get(ENTRY_TYPE)
    if entry_type == ENTRY_TYPE_LISTENER:
        port = int(entry.options.get(CONF_PORT, entry.data.get(CONF_PORT, DEFAULT_PORT)))

        await _start_listener(hass, port)

        async def _options_updated(hass: HomeAssistant, updated_entry: ConfigEntry) -> None:
            await hass.config_entries.async_reload(updated_entry.entry_id)

        entry.async_on_unload(entry.add_update_listener(_options_updated))

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    if entry_type == ENTRY_TYPE_DEVICE:
        # Device entries only create entities; listener entry provides the server.
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    _LOGGER.warning("Unknown entry type for %s: %s", entry.title, entry_type)
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_type = entry.data.get(ENTRY_TYPE)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    if entry_type == ENTRY_TYPE_LISTENER:
        # If no other listener entries exist, stop the server.
        other_listeners = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and e.data.get(ENTRY_TYPE) == ENTRY_TYPE_LISTENER
        ]
        if not other_listeners:
            await _stop_listener(hass)

    return True
