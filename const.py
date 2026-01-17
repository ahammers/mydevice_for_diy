"""Constants for the MyDevice for DIY integration."""

DOMAIN = "mydevice_for_diy"

# Entry types: we keep exactly one listener entry and N device entries.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_LISTENER = "listener"
ENTRY_TYPE_DEVICE = "device"

# Listener config
CONF_PORT = "port"
DEFAULT_PORT = 55355

# Device config (stored in the device entry)
CONF_DEVICE_ID = "device_id"          # unique-device-id
CONF_DEVICE_TYPE = "device_type"      # device-type-id (currently only "ht")
CONF_NAME = "name"                    # friendly name in HA

# Supported device types
SUPPORTED_DEVICE_TYPES = {"ht"}

# Dispatcher signal prefix. Full signal is f"{SIGNAL_DATA_RECEIVED}_{device_id}".
SIGNAL_DATA_RECEIVED = f"{DOMAIN}_data_received"
