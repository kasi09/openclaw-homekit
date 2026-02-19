"""Tests for HomeKitSkill - all aiohomekit calls are mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openclaw_homekit.skill import HomeKitSkill


@pytest.fixture
def skill(tmp_path):
    """Create a HomeKitSkill with a temporary pairing file."""
    pairing_file = str(tmp_path / "test_pairings.json")
    return HomeKitSkill(pairing_file=pairing_file)


@pytest.fixture
def mock_controller():
    """Create a mock aiohomekit Controller."""
    ctrl = MagicMock()
    ctrl.pairings = {}
    ctrl.aliases = {}
    ctrl.discover = AsyncMock(return_value=[])
    ctrl.pair = AsyncMock()
    ctrl.load_data = MagicMock()
    ctrl.save_data = MagicMock()
    return ctrl


def _make_discovery(name="Test Light", device_id="AA:BB:CC:DD:EE:FF", model="LIFX"):
    """Helper to create a mock discovery result."""
    discovery = MagicMock()
    discovery.info = {
        "name": name,
        "id": device_id,
        "md": model,
        "c#": 1,
        "s#": 1,
        "ci": 5,
        "sf": 0,
    }
    return discovery


def _make_pairing(accessories_data=None):
    """Helper to create a mock pairing."""
    pairing = AsyncMock()
    pairing.pairing_data = {"AccessoryIP": "192.168.1.100", "AccessoryPort": 51826}
    pairing.list_accessories_and_characteristics = AsyncMock(return_value=accessories_data or [])
    pairing.get_characteristics = AsyncMock(return_value={})
    pairing.put_characteristics = AsyncMock()
    pairing.close = AsyncMock()
    return pairing


# --- describe ---


def test_describe(skill):
    """Test skill metadata."""
    desc = skill.describe()
    assert desc["name"] == "homekit"
    assert desc["version"] == "1.0.0"


# --- discover ---


def test_discover_finds_devices(skill, mock_controller):
    """Test discovering HomeKit devices on the network."""
    devices = [
        _make_discovery("Living Room Light", "AA:BB:CC:DD:EE:FF", "LIFX"),
        _make_discovery("Thermostat", "11:22:33:44:55:66", "Ecobee"),
    ]
    mock_controller.discover.return_value = devices

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("discover", {})

    assert result["count"] == 2
    assert result["devices"][0]["name"] == "Living Room Light"
    assert result["devices"][0]["id"] == "AA:BB:CC:DD:EE:FF"
    assert result["devices"][1]["model"] == "Ecobee"


def test_discover_empty_network(skill, mock_controller):
    """Test discovering when no devices are found."""
    mock_controller.discover.return_value = []

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("discover", {})

    assert result["count"] == 0
    assert result["devices"] == []


def test_discover_with_timeout(skill, mock_controller):
    """Test discovering with a custom timeout."""
    mock_controller.discover.return_value = []

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        skill.process("discover", {"timeout": 5})

    mock_controller.discover.assert_called_once_with(timeout=5)


# --- pair ---


def test_pair_success(skill, mock_controller):
    """Test successfully pairing with a device."""
    pairing = _make_pairing([])
    mock_controller.pair.return_value = pairing

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("pair", {"device_id": "AA:BB:CC:DD:EE:FF", "pin": "123-45-678"})

    assert result["success"] is True
    assert result["device_id"] == "AA:BB:CC:DD:EE:FF"
    mock_controller.pair.assert_called_once_with("AA:BB:CC:DD:EE:FF", "123-45-678")


def test_pair_missing_device_id(skill):
    """Test pairing without device_id raises error."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("pair", {"pin": "123-45-678"})


def test_pair_missing_pin(skill):
    """Test pairing without PIN raises error."""
    with pytest.raises(ValueError, match="Missing required parameter: pin"):
        skill.process("pair", {"device_id": "AA:BB:CC:DD:EE:FF"})


def test_pair_saves_pairings(skill, mock_controller):
    """Test that pairing saves the pairing data to file."""
    pairing = _make_pairing([])
    mock_controller.pair.return_value = pairing

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        skill._controller = mock_controller
        skill.process("pair", {"device_id": "AA:BB:CC:DD:EE:FF", "pin": "123-45-678"})

    mock_controller.save_data.assert_called_once_with(skill.pairing_file)


# --- unpair ---


def test_unpair_success(skill, mock_controller):
    """Test successfully unpairing a device."""
    pairing = _make_pairing()
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        skill._controller = mock_controller
        result = skill.process("unpair", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["success"] is True
    assert result["device_id"] == "AA:BB:CC:DD:EE:FF"
    pairing.close.assert_called_once()


def test_unpair_unknown_device(skill, mock_controller):
    """Test unpairing a device that is not paired."""
    mock_controller.pairings = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(ValueError, match="No pairing found for device"):
            skill.process("unpair", {"device_id": "unknown"})


def test_unpair_missing_device_id(skill):
    """Test unpairing without device_id raises error."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("unpair", {})


# --- list_accessories ---


def test_list_accessories(skill, mock_controller):
    """Test listing accessories for a paired device."""
    pairing = _make_pairing([{"aid": 1, "services": [{"type": "light", "characteristics": []}]}])
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("list_accessories", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["device_id"] == "AA:BB:CC:DD:EE:FF"
    assert isinstance(result["accessories"], list)


def test_list_accessories_unknown_device(skill, mock_controller):
    """Test listing accessories for an unpaired device."""
    mock_controller.pairings = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(ValueError, match="No pairing found for device"):
            skill.process("list_accessories", {"device_id": "unknown"})


def test_list_accessories_missing_device_id(skill):
    """Test listing accessories without device_id raises error."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("list_accessories", {})


# --- get_characteristic ---


def test_get_characteristic(skill, mock_controller):
    """Test reading a characteristic value."""
    pairing = _make_pairing()
    pairing.get_characteristics.return_value = {(1, 10): {"value": True}}
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process(
            "get_characteristic",
            {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1, "iid": 10},
        )

    assert result["value"] is True
    assert result["aid"] == 1
    assert result["iid"] == 10


def test_get_characteristic_missing_params(skill):
    """Test get_characteristic with missing parameters."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("get_characteristic", {"aid": 1, "iid": 10})

    with pytest.raises(ValueError, match="Missing required parameter: aid"):
        skill.process("get_characteristic", {"device_id": "AA:BB:CC:DD:EE:FF", "iid": 10})

    with pytest.raises(ValueError, match="Missing required parameter: iid"):
        skill.process("get_characteristic", {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1})


# --- set_characteristic ---


def test_set_characteristic(skill, mock_controller):
    """Test writing a characteristic value."""
    pairing = _make_pairing()
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process(
            "set_characteristic",
            {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1, "iid": 10, "value": 75},
        )

    assert result["success"] is True
    assert result["value"] == 75
    pairing.put_characteristics.assert_called_once_with([(1, 10, 75)])


def test_set_characteristic_missing_value(skill):
    """Test set_characteristic without value raises error."""
    with pytest.raises(ValueError, match="Missing required parameter: value"):
        skill.process(
            "set_characteristic",
            {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1, "iid": 10},
        )


def test_set_characteristic_missing_params(skill):
    """Test set_characteristic with missing parameters."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("set_characteristic", {"aid": 1, "iid": 10, "value": 1})

    with pytest.raises(ValueError, match="Missing required parameter: aid"):
        skill.process(
            "set_characteristic",
            {"device_id": "AA:BB:CC:DD:EE:FF", "iid": 10, "value": 1},
        )

    with pytest.raises(ValueError, match="Missing required parameter: iid"):
        skill.process(
            "set_characteristic",
            {"device_id": "AA:BB:CC:DD:EE:FF", "aid": 1, "value": 1},
        )


# --- list_pairings ---


def test_list_pairings_empty(skill, mock_controller):
    """Test listing pairings when no pairings exist."""
    mock_controller.aliases = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("list_pairings", {})

    assert result["count"] == 0
    assert result["pairings"] == []


def test_list_pairings_with_data(skill, mock_controller):
    """Test listing pairings when pairings exist."""
    mock_controller.aliases = {
        "AA:BB:CC:DD:EE:FF": MagicMock(),
        "11:22:33:44:55:66": MagicMock(),
    }

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("list_pairings", {})

    assert result["count"] == 2
    device_ids = [p["device_id"] for p in result["pairings"]]
    assert "AA:BB:CC:DD:EE:FF" in device_ids
    assert "11:22:33:44:55:66" in device_ids


# --- unknown action ---


def test_unknown_action(skill):
    """Test that an unknown action raises ValueError."""
    with pytest.raises(ValueError, match="Unknown action: foobar"):
        skill.process("foobar", {})


# --- network errors ---


def test_discover_network_error(skill, mock_controller):
    """Test discovery when network error occurs."""
    mock_controller.discover.side_effect = OSError("Network unreachable")

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(OSError, match="Network unreachable"):
            skill.process("discover", {})


def test_pair_wrong_pin(skill, mock_controller):
    """Test pairing with wrong PIN."""
    mock_controller.pair.side_effect = Exception("M6 Verification failed")

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(Exception, match="M6 Verification failed"):
            skill.process("pair", {"device_id": "AA:BB:CC:DD:EE:FF", "pin": "000-00-000"})


# --- controller initialization ---


def test_get_controller_loads_pairings(skill, tmp_path):
    """Test that _get_controller calls load_data."""
    with patch("openclaw_homekit.skill.Controller") as mock_ctrl_cls:
        mock_ctrl = MagicMock()
        mock_ctrl_cls.return_value = mock_ctrl
        controller = skill._get_controller()

    assert controller is mock_ctrl
    mock_ctrl.load_data.assert_called_once_with(skill.pairing_file)


def test_get_controller_reuses_instance(skill, mock_controller):
    """Test that _get_controller reuses the controller."""
    skill._controller = mock_controller
    controller = skill._get_controller()
    assert controller is mock_controller


# --- async bridge ---


def test_ensure_loop_creates_thread(skill):
    """Test that _ensure_loop creates a background thread."""
    loop = skill._ensure_loop()
    assert loop is not None
    assert loop.is_running()
    # Cleanup
    loop.call_soon_threadsafe(loop.stop)


def test_run_async_executes_coroutine(skill):
    """Test that _run_async properly executes a coroutine."""

    async def dummy():
        return 42

    result = skill._run_async(dummy())
    assert result == 42
    # Cleanup
    if skill._loop:
        skill._loop.call_soon_threadsafe(skill._loop.stop)


# --- identify ---


def test_identify_success(skill, mock_controller):
    """Test triggering device identification."""
    pairing = _make_pairing()
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("identify", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["identified"] is True
    assert result["device_id"] == "AA:BB:CC:DD:EE:FF"
    pairing.identify.assert_called_once()


def test_identify_missing_device_id(skill):
    """Test identify without device_id raises error."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("identify", {})


def test_identify_unknown_device(skill, mock_controller):
    """Test identify for an unpaired device."""
    mock_controller.pairings = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(ValueError, match="No pairing found for device"):
            skill.process("identify", {"device_id": "unknown"})


# --- get_all_characteristics ---


def test_get_all_characteristics(skill, mock_controller):
    """Test reading all characteristics for a device."""
    accessories = [
        {
            "aid": 1,
            "services": [
                {
                    "type": "light",
                    "characteristics": [
                        {"iid": 10, "type": "on", "value": True},
                        {"iid": 11, "type": "brightness", "value": 75},
                    ],
                }
            ],
        }
    ]
    pairing = _make_pairing(accessories)
    pairing.get_characteristics.return_value = {
        (1, 10): {"value": True},
        (1, 11): {"value": 75},
    }
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("get_all_characteristics", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["device_id"] == "AA:BB:CC:DD:EE:FF"
    assert result["count"] == 2


def test_get_all_characteristics_empty_device(skill, mock_controller):
    """Test reading characteristics for a device with no services."""
    pairing = _make_pairing([{"aid": 1, "services": []}])
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("get_all_characteristics", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["count"] == 0
    assert result["characteristics"] == []


def test_get_all_characteristics_missing_device_id(skill):
    """Test get_all_characteristics without device_id."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("get_all_characteristics", {})


def test_get_all_characteristics_unknown_device(skill, mock_controller):
    """Test get_all_characteristics for unpaired device."""
    mock_controller.pairings = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(ValueError, match="No pairing found for device"):
            skill.process("get_all_characteristics", {"device_id": "unknown"})


def test_get_all_characteristics_multiple_accessories(skill, mock_controller):
    """Test reading characteristics from multiple accessories."""
    accessories = [
        {
            "aid": 1,
            "services": [
                {"type": "light", "characteristics": [{"iid": 10, "type": "on", "value": True}]}
            ],
        },
        {
            "aid": 2,
            "services": [
                {"type": "sensor", "characteristics": [{"iid": 20, "type": "temp", "value": 22}]}
            ],
        },
    ]
    pairing = _make_pairing(accessories)
    pairing.get_characteristics.return_value = {
        (1, 10): {"value": True},
        (2, 20): {"value": 22},
    }
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("get_all_characteristics", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["count"] == 2


# --- set_multiple ---


def test_set_multiple(skill, mock_controller):
    """Test setting multiple characteristics at once."""
    pairing = _make_pairing()
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process(
            "set_multiple",
            {
                "device_id": "AA:BB:CC:DD:EE:FF",
                "characteristics": [
                    {"aid": 1, "iid": 10, "value": True},
                    {"aid": 1, "iid": 11, "value": 75},
                ],
            },
        )

    assert result["success"] is True
    assert result["count"] == 2
    pairing.put_characteristics.assert_called_once_with([(1, 10, True), (1, 11, 75)])


def test_set_multiple_single(skill, mock_controller):
    """Test setting a single characteristic via set_multiple."""
    pairing = _make_pairing()
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process(
            "set_multiple",
            {
                "device_id": "AA:BB:CC:DD:EE:FF",
                "characteristics": [{"aid": 1, "iid": 10, "value": False}],
            },
        )

    assert result["success"] is True
    assert result["count"] == 1


def test_set_multiple_missing_device_id(skill):
    """Test set_multiple without device_id."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("set_multiple", {"characteristics": [{"aid": 1, "iid": 1, "value": 1}]})


def test_set_multiple_missing_characteristics(skill):
    """Test set_multiple without characteristics."""
    with pytest.raises(ValueError, match="Missing required parameter: characteristics"):
        skill.process("set_multiple", {"device_id": "AA:BB:CC:DD:EE:FF"})


def test_set_multiple_invalid_format(skill):
    """Test set_multiple with invalid characteristic format."""
    with pytest.raises(ValueError, match="Each characteristic must have aid, iid, and value"):
        skill.process(
            "set_multiple",
            {
                "device_id": "AA:BB:CC:DD:EE:FF",
                "characteristics": [{"aid": 1, "iid": 10}],  # missing value
            },
        )


def test_set_multiple_unknown_device(skill, mock_controller):
    """Test set_multiple for unpaired device."""
    mock_controller.pairings = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(ValueError, match="No pairing found for device"):
            skill.process(
                "set_multiple",
                {
                    "device_id": "unknown",
                    "characteristics": [{"aid": 1, "iid": 10, "value": True}],
                },
            )


# --- get_device_info ---


def test_get_device_info(skill, mock_controller):
    """Test reading device information."""
    accessories = [
        {
            "aid": 1,
            "services": [
                {
                    "type": "0000003E-0000-1000-8000-0026BB765291",
                    "characteristics": [
                        {"type": "00000020", "value": "TestCorp"},
                        {"type": "00000021", "value": "LightBulb"},
                        {"type": "00000023", "value": "My Light"},
                        {"type": "00000030", "value": "SN12345"},
                        {"type": "00000052", "value": "1.2.3"},
                        {"type": "00000053", "value": "1.0.0"},
                    ],
                }
            ],
        }
    ]
    pairing = _make_pairing(accessories)
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("get_device_info", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["manufacturer"] == "TestCorp"
    assert result["model"] == "LightBulb"
    assert result["name"] == "My Light"
    assert result["serial_number"] == "SN12345"
    assert result["firmware_revision"] == "1.2.3"
    assert result["hardware_revision"] == "1.0.0"


def test_get_device_info_partial(skill, mock_controller):
    """Test device info with some fields missing."""
    accessories = [
        {
            "aid": 1,
            "services": [
                {
                    "type": "3E",
                    "characteristics": [
                        {"type": "20", "value": "ACME"},
                        {"type": "21", "value": "Widget"},
                    ],
                }
            ],
        }
    ]
    pairing = _make_pairing(accessories)
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("get_device_info", {"device_id": "AA:BB:CC:DD:EE:FF"})

    assert result["manufacturer"] == "ACME"
    assert result["model"] == "Widget"
    assert result["serial_number"] == ""
    assert result["firmware_revision"] == ""


def test_get_device_info_missing_device_id(skill):
    """Test get_device_info without device_id."""
    with pytest.raises(ValueError, match="Missing required parameter: device_id"):
        skill.process("get_device_info", {})


def test_get_device_info_unknown_device(skill, mock_controller):
    """Test get_device_info for unpaired device."""
    mock_controller.pairings = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        with pytest.raises(ValueError, match="No pairing found for device"):
            skill.process("get_device_info", {"device_id": "unknown"})


# --- device_summary ---


def test_device_summary_with_devices(skill, mock_controller):
    """Test device summary with paired devices."""
    pairing = _make_pairing([{"aid": 1, "services": [{"type": "light", "characteristics": []}]}])
    mock_controller.aliases = {"AA:BB:CC:DD:EE:FF": MagicMock()}
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("device_summary", {})

    assert result["count"] == 1
    assert result["devices"][0]["device_id"] == "AA:BB:CC:DD:EE:FF"
    assert result["devices"][0]["reachable"] is True


def test_device_summary_empty(skill, mock_controller):
    """Test device summary with no devices."""
    mock_controller.aliases = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("device_summary", {})

    assert result["count"] == 0
    assert result["devices"] == []


def test_device_summary_unreachable(skill, mock_controller):
    """Test device summary with unreachable device."""
    pairing = _make_pairing()
    pairing.list_accessories_and_characteristics.side_effect = OSError("Timeout")
    mock_controller.aliases = {"AA:BB:CC:DD:EE:FF": MagicMock()}
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("device_summary", {})

    assert result["count"] == 1
    assert result["devices"][0]["reachable"] is False


def test_device_summary_mixed(skill, mock_controller):
    """Test device summary with mix of reachable and unreachable."""
    pairing_ok = _make_pairing([{"aid": 1, "services": []}])
    pairing_bad = _make_pairing()
    pairing_bad.list_accessories_and_characteristics.side_effect = OSError("Timeout")

    mock_controller.aliases = {
        "AA:BB:CC:DD:EE:FF": MagicMock(),
        "11:22:33:44:55:66": MagicMock(),
    }
    mock_controller.pairings = {
        "AA:BB:CC:DD:EE:FF": pairing_ok,
        "11:22:33:44:55:66": pairing_bad,
    }

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("device_summary", {})

    assert result["count"] == 2
    reachable = [d for d in result["devices"] if d["reachable"]]
    unreachable = [d for d in result["devices"] if not d["reachable"]]
    assert len(reachable) == 1
    assert len(unreachable) == 1


# --- health_check ---


def test_health_check_all_reachable(skill, mock_controller):
    """Test health check when all devices are reachable."""
    pairing = _make_pairing([])
    mock_controller.aliases = {"AA:BB:CC:DD:EE:FF": MagicMock()}
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("health_check", {})

    assert result["total"] == 1
    assert result["reachable"] == 1
    assert result["unreachable"] == 0


def test_health_check_all_unreachable(skill, mock_controller):
    """Test health check when all devices are unreachable."""
    pairing = _make_pairing()
    pairing.list_accessories_and_characteristics.side_effect = OSError("Timeout")
    mock_controller.aliases = {"AA:BB:CC:DD:EE:FF": MagicMock()}
    mock_controller.pairings = {"AA:BB:CC:DD:EE:FF": pairing}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("health_check", {})

    assert result["total"] == 1
    assert result["reachable"] == 0
    assert result["unreachable"] == 1
    assert "error" in result["devices"][0]


def test_health_check_mixed(skill, mock_controller):
    """Test health check with mix of reachable and unreachable."""
    pairing_ok = _make_pairing([])
    pairing_bad = _make_pairing()
    pairing_bad.list_accessories_and_characteristics.side_effect = OSError("Timeout")

    mock_controller.aliases = {
        "AA:BB:CC:DD:EE:FF": MagicMock(),
        "11:22:33:44:55:66": MagicMock(),
    }
    mock_controller.pairings = {
        "AA:BB:CC:DD:EE:FF": pairing_ok,
        "11:22:33:44:55:66": pairing_bad,
    }

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("health_check", {})

    assert result["total"] == 2
    assert result["reachable"] == 1
    assert result["unreachable"] == 1


def test_health_check_no_devices(skill, mock_controller):
    """Test health check with no paired devices."""
    mock_controller.aliases = {}

    with patch.object(skill, "_get_controller", return_value=mock_controller):
        result = skill.process("health_check", {})

    assert result["total"] == 0
    assert result["reachable"] == 0
