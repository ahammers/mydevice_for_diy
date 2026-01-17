# MyDevice for DIY (Home Assistant)

A small Home Assistant custom integration that lets your DIY devices **push** sensor data to Home Assistant via a simple TCP JSON protocol.

- **Listener:** Home Assistant listens on TCP **port 55355** (configurable).
- **Discovery:** If an unknown device sends data, it will show up under **Settings → Devices & services → Discovered**.
- **Entities:** Once you add the discovered device, the integration creates entities and updates them on every packet.

Currently supported device types:

- `ht` (Humidity + Temperature)
  - `data.t` → temperature in **°C** (float)
  - `data.h` → humidity in **%** (float)

---

## Protocol

TCP is a byte stream. To keep parsing simple and robust, this integration uses **NDJSON**:

> One JSON object per line, terminated with `\n`.

### Packet format

```json
{
  "device": "<unique-device-id>",
  "type": "<device-type-id>",
  "data": {
    "t": 21.3,
    "h": 45.6
  }
}
```

### Example (one line)

```text
{"device":"ABC123","type":"ht","data":{"t":21.3,"h":45.6}}\n
```

### Notes

- Unknown keys inside `data` are ignored for now.
- Invalid JSON lines are ignored.
- Values are stored as **last received** values.

---

## Installation (HACS Custom Repository)

1. In Home Assistant open **HACS → Integrations**
2. Open the menu (⋮) → **Custom repositories**
3. Add your GitHub repo URL, choose category **Integration**
4. Install **MyDevice for DIY**
5. Restart Home Assistant
6. Go to **Settings → Devices & services → Add integration** and search for **MyDevice for DIY**
7. Configure the listener port (default: 55355)

After that, devices that send packets will appear as **Discovered**.

---

## Usage

### 1) Add the listener

Add the integration once to create the *listener* entry. This starts the TCP server.

### 2) Send data from a device

Send one JSON line per measurement.

#### Quick test from a shell

```bash
printf '{"device":"TEST01","type":"ht","data":{"t":22.5,"h":40.0}}\n' | nc -w 1 <homeassistant-ip> 55355
```

#### Minimal C++ example (POSIX sockets)

```cpp
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstring>
#include <string>

static bool send_line(const char* host, int port, const std::string& line)
{
    const int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return false;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port));
    if (::inet_pton(AF_INET, host, &addr.sin_addr) != 1) {
        ::close(fd);
        return false;
    }

    if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        ::close(fd);
        return false;
    }

    const std::string payload = line + "\n"; // NDJSON: one JSON object per line
    const ssize_t n = ::send(fd, payload.data(), payload.size(), 0);
    ::close(fd);
    return n == static_cast<ssize_t>(payload.size());
}

int main()
{
    const std::string json = R"({"device":"ABC123","type":"ht","data":{"t":21.3,"h":45.6}})";
    return send_line("192.168.1.10", 55355, json) ? 0 : 1;
}
```

### 3) Finish device setup in Home Assistant

- Go to **Settings → Devices & services**
- Under **Discovered**, click the new device
- Give it a name and finish setup

The integration creates:

- `<name> Temperature` (°C)
- `<name> Humidity` (%)

---

## Security considerations

This is a LAN push protocol. On purpose it is minimal and does **not** include authentication.

Recommended:

- Only expose the TCP port inside your local network.
- Use firewall/VLAN rules to limit who can connect.
- If you need authentication/TLS, open an issue or add it yourself (see "Roadmap").

---

## Troubleshooting

### No device appears under "Discovered"

- Make sure you added the integration once (listener entry exists).
- Check that the port is reachable from the device.
- Ensure you send **one JSON object per line** and terminate with `\n`.

### Entities do not update

- Verify the device was added (not only discovered).
- Ensure the packet uses the configured `device` id.

### Logs

Enable debug logs in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.mydevice_for_diy: debug
```

---

## Roadmap ideas

- Optional shared secret / token
- TLS support
- More device types and dynamic entity mapping
- Rate limiting / connection pooling

---

## License

MIT (recommended for HACS repos) - add your preferred license file.
