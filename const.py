"""Constants for the raumthermometer integration."""

DOMAIN = "raumthermometer"

CONF_PORT = "port"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"

DEFAULT_PORT = 45678

# Internal entry types
ENTRY_TYPE = "entry_type"
ENTRY_TYPE_LISTENER = "listener"
ENTRY_TYPE_DEVICE = "device"

# Dispatcher signal
SIGNAL_DEVICE_UPDATED = f"{DOMAIN}_device_updated"
