"""Tests for the Shure SLX-D TCP client."""

from custom_components.shure_slxd.client import ReceiverData, ShureClient, _parse_int


def test_parse_rep_device_model():
    """Test parsing a device model response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 0 MODEL {SLXD4D} >", data)
    assert data.device.model == "SLXD4D"


def test_parse_rep_device_fw_ver():
    """Test parsing firmware version response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 0 FW_VER {2.3.15} >", data)
    assert data.device.fw_ver == "2.3.15"


def test_parse_rep_device_id():
    """Test parsing device ID response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 0 DEVICE_ID {00A0AE123456} >", data)
    assert data.device.device_id == "00A0AE123456"


def test_parse_rep_battery_bars():
    """Test parsing battery bars response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATTERY_BARS 004 >", data)
    assert data.channels[1].battery_bars == 4


def test_parse_rep_battery_charge():
    """Test parsing battery charge response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATTERY_CHARGE 075 >", data)
    assert data.channels[1].battery_charge == 75


def test_parse_rep_battery_bars_unknown():
    """Test parsing battery bars with unknown value (255)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATTERY_BARS 255 >", data)
    assert data.channels[1].battery_bars is None


def test_parse_rep_battery_run_time_unknown():
    """Test parsing battery run time with unknown sentinel (65535)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATTERY_RUN_TIME 65535 >", data)
    assert data.channels[1].battery_run_time is None


def test_parse_rep_battery_run_time_valid():
    """Test parsing battery run time with valid value."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATTERY_RUN_TIME 00120 >", data)
    assert data.channels[1].battery_run_time == 120


def test_parse_rep_chan_name():
    """Test parsing channel name response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 CHAN_NAME {Pastor} >", data)
    assert data.channels[1].chan_name == "Pastor"


def test_parse_rep_tx_type():
    """Test parsing transmitter type response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 2 TX_TYPE SLXD1 >", data)
    assert data.channels[2].tx_type == "SLXD1"


def test_parse_rep_frequency():
    """Test parsing frequency response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 FREQUENCY 470000 >", data)
    assert data.channels[1].frequency == "470000"


def test_parse_rep_rf_int_det():
    """Test parsing RF interference response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 RF_INT_DET NONE >", data)
    assert data.channels[1].rf_int_det == "NONE"


def test_parse_rep_antenna():
    """Test parsing antenna response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 ANTENNA A >", data)
    assert data.channels[1].antenna == "A"


def test_parse_sample():
    """Test parsing a SAMPLE line with RF and audio levels."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< SAMPLE 1 ALL 045 038 012 >", data)
    assert data.channels[1].rf_level_a == 45
    assert data.channels[1].rf_level_b == 38
    assert data.channels[1].audio_level == 12


def test_parse_multiple_channels():
    """Test parsing responses for multiple channels."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATTERY_BARS 005 >", data)
    client._parse_response("< REP 2 BATTERY_BARS 003 >", data)
    assert data.channels[1].battery_bars == 5
    assert data.channels[2].battery_bars == 3


def test_parse_unknown_line():
    """Test that unknown lines are silently ignored."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("some garbage line", data)
    assert len(data.channels) == 0


def test_parse_int_valid():
    """Test _parse_int with valid values."""
    assert _parse_int("042") == 42
    assert _parse_int("0") == 0
    assert _parse_int("100") == 100


def test_parse_int_sentinels():
    """Test _parse_int returns None for sentinel values."""
    assert _parse_int("255") is None
    assert _parse_int("65535") is None


def test_parse_int_invalid():
    """Test _parse_int with invalid values."""
    assert _parse_int("abc") is None
    assert _parse_int("") is None
