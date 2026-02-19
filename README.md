# openclaw-homekit

[![Tests](https://github.com/kasi09/openclaw-homekit/actions/workflows/tests.yml/badge.svg)](https://github.com/kasi09/openclaw-homekit/actions/workflows/tests.yml)

HomeKit Skill for [OpenClaw](https://github.com/kasi09/openclaw-python) — direct HomeKit device control via [aiohomekit](https://github.com/Jc2k/aiohomekit), without requiring Homebridge or Home Assistant as middleware.

## Features

- **Native HomeKit Protocol** — communicates directly with HomeKit accessories over your local network
- **Device Discovery** — finds HomeKit devices via mDNS/Bonjour
- **Pairing & Unpairing** — pair with devices using their setup PIN
- **Characteristic Read/Write** — read and control any HomeKit characteristic (lights, switches, sensors, etc.)
- **Persistent Pairings** — pairing data is saved to a JSON file for reuse across sessions

## Requirements

- Python 3.10+
- Local network access (mDNS/Bonjour must be reachable)
- HomeKit-compatible devices on the same network

## Installation

```bash
pip install "openclaw-python-skill @ git+https://github.com/kasi09/openclaw-python.git"
pip install "openclaw-homekit @ git+https://github.com/kasi09/openclaw-homekit.git"
```

## Quick Start

```python
from openclaw_homekit import HomeKitSkill

skill = HomeKitSkill(pairing_file="my_pairings.json")

# Discover devices on the network
result = skill.process("discover", {"timeout": 10})
print(result)
# {"devices": [{"name": "Living Room Light", "id": "AA:BB:CC:DD:EE:FF", ...}], "count": 1}

# Pair with a device using its PIN
result = skill.process("pair", {"device_id": "AA:BB:CC:DD:EE:FF", "pin": "123-45-678"})

# Read a characteristic (e.g., light on/off state)
result = skill.process("get_characteristic", {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1, "iid": 10})
print(result["value"])  # True

# Set a characteristic (e.g., brightness to 75%)
skill.process("set_characteristic", {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1, "iid": 11, "value": 75})
```

## Actions

| Action | Parameters | Description |
|--------|-----------|-------------|
| `discover` | `timeout?` (default 10) | Find HomeKit devices on the local network |
| `pair` | `device_id`, `pin` | Pair with a device (PIN format: XXX-XX-XXX) |
| `unpair` | `device_id` | Remove a pairing |
| `list_accessories` | `device_id` | List all accessories and services for a paired device |
| `get_characteristic` | `device_id`, `aid`, `iid` | Read a characteristic value |
| `set_characteristic` | `device_id`, `aid`, `iid`, `value` | Write a characteristic value |
| `list_pairings` | — | List all stored pairings |

### Pairing PIN

HomeKit devices display a setup code during pairing, formatted as `XXX-XX-XXX` (e.g., `123-45-678`). You can usually find it on the device itself or in its documentation.

### Accessories, Services & Characteristics

HomeKit devices are organized as:
- **Accessory** (aid) — a physical device
- **Service** — a function of the device (e.g., Lightbulb, Thermostat)
- **Characteristic** (iid) — a property of the service (e.g., On, Brightness, Temperature)

Use `list_accessories` to see all services and characteristics with their `aid`/`iid` values.

## Architecture

The skill uses a background thread with its own asyncio event loop to bridge the synchronous `process()` interface with aiohomekit's async API. This allows seamless integration with the OpenClaw skill framework.

```
process() → _run_async(coroutine) → background event loop → aiohomekit async calls
```

## Development

```bash
git clone https://github.com/kasi09/openclaw-homekit.git
cd openclaw-homekit
pip install "openclaw-python-skill @ git+https://github.com/kasi09/openclaw-python.git"
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint & format
ruff check src tests
ruff format src tests

# Type check
mypy src
```

## Support

<a href="https://www.buymeacoffee.com/kasi09" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

## License

MIT
