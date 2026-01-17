"""Sensor entities for MyDevice for DIY."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    DOMAIN,
    ENTRY_TYPE_DEVICE,
    SIGNAL_DATA_RECEIVED,
)


def _data_signal(device_id: str) -> str:
    return f"{SIGNAL_DATA_RECEIVED}_{device_id}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up sensors for a discovered/configured device."""
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_TYPE_DEVICE:
        return

    device_id = str(entry.data[CONF_DEVICE_ID])
    device_type = str(entry.data[CONF_DEVICE_TYPE])
    name = str(entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, entry.title)))

    entities: list[SensorEntity] = []

    # Currently only the "ht" device type is supported.
    if device_type == "ht":
        entities.append(_TemperatureSensor(hass, device_id, name))
        entities.append(_HumiditySensor(hass, device_id, name))

    async_add_entities(entities)


class _BaseMyDeviceSensor(SensorEntity):
    """Base class that pulls the latest value from hass.data and updates via dispatcher."""

    def __init__(self, hass: HomeAssistant, device_id: str, base_name: str) -> None:
        self.hass = hass
        self._device_id = device_id
        self._base_name = base_name
        self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        # This groups the sensors into one HA device.
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._base_name,
            manufacturer="MyDevice for DIY",
            model="TCP JSON Push",
        )

    async def async_added_to_hass(self) -> None:
        # Update when new data arrives.
        self._unsub = async_dispatcher_connect(self.hass, _data_signal(self._device_id), self._handle_update)
        self._handle_update()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    def _get_value(self, key: str):
        return self.hass.data[DOMAIN]["values"].get(self._device_id, {}).get(key)


class _TemperatureSensor(_BaseMyDeviceSensor):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, device_id: str, base_name: str) -> None:
        super().__init__(hass, device_id, base_name)
        self._attr_unique_id = f"{device_id}_t"
        self._attr_name = f"{base_name} Temperature"

    @property
    def native_value(self):
        return self._get_value("t")


class _HumiditySensor(_BaseMyDeviceSensor):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, device_id: str, base_name: str) -> None:
        super().__init__(hass, device_id, base_name)
        self._attr_unique_id = f"{device_id}_h"
        self._attr_name = f"{base_name} Humidity"

    @property
    def native_value(self):
        return self._get_value("h")
