"""Sensor platform for MyDeviceForDIY."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
    ENTRY_TYPE,
    ENTRY_TYPE_DEVICE,
    SIGNAL_DEVICE_UPDATED,
)


@dataclass(frozen=True)
class _Field:
    key: str
    name: str
    unit: str | None
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None


FIELDS: list[_Field] = [
    _Field(
        key="temperature",
        name="Temperature",
        unit="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _Field(
        key="humidity",
        name="Humidity",
        unit="%",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    if entry.data.get(ENTRY_TYPE) != ENTRY_TYPE_DEVICE:
        return

    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, device_id)

    entities: list[SensorEntity] = []
    for f in FIELDS:
        entities.append(MyDeviceForDIYSensor(hass, device_id, device_name, f))

    async_add_entities(entities)


class MyDeviceForDIYSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, device_id: str, device_name: str, field: _Field) -> None:
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._field = field

        self._attr_unique_id = f"{DOMAIN}_{device_id}_{field.key}"
        self._attr_name = field.name
        self._attr_native_unit_of_measurement = field.unit
        self._attr_device_class = field.device_class
        self._attr_state_class = field.state_class

        self._unsub: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Custom (ESP32)",
            model="MyDeviceForDIY",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self.hass.data[DOMAIN]["devices"].get(self._device_id)
        if st is None:
            return {}
        attrs: dict[str, Any] = {}
        if st.last_update_utc is not None:
            attrs["measurement_ts_utc"] = st.last_update_utc
        if st.last_seen_utc is not None:
            attrs["last_seen_utc"] = st.last_seen_utc
        return attrs

    @property
    def native_value(self) -> float | None:
        st = self.hass.data[DOMAIN]["devices"].get(self._device_id)
        if st is None:
            return None
        if self._field.key == "temperature":
            return st.temperature_c
        if self._field.key == "humidity":
            return st.humidity_percent
        return None

    async def async_added_to_hass(self) -> None:
        @callback
        def _updated(updated_device_id: str) -> None:
            if updated_device_id == self._device_id:
                self.async_write_ha_state()

        self._unsub = async_dispatcher_connect(self.hass, SIGNAL_DEVICE_UPDATED, _updated)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
