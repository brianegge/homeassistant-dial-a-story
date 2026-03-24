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


def test_parse_rep_rf_band():
    """Test parsing RF band response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 0 RF_BAND {G55} >", data)
    assert data.device.rf_band == "G55"


def test_parse_rep_batt_bars():
    """Test parsing battery bars response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_BARS 004 >", data)
    assert data.channels[1].batt_bars == 4


def test_parse_rep_batt_charge():
    """Test parsing battery charge response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_CHARGE 075 >", data)
    assert data.channels[1].batt_charge == 75


def test_parse_rep_batt_bars_unknown():
    """Test parsing battery bars with unknown value (255 = no transmitter)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_BARS 255 >", data)
    assert data.channels[1].batt_bars is None


def test_parse_rep_batt_run_time_unknown():
    """Test parsing battery run time with unknown sentinel (65535)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_RUN_TIME 65535 >", data)
    assert data.channels[1].batt_run_time is None


def test_parse_rep_batt_run_time_calculating():
    """Test parsing battery run time while calculating (65534)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_RUN_TIME 65534 >", data)
    assert data.channels[1].batt_run_time is None


def test_parse_rep_batt_run_time_valid():
    """Test parsing battery run time with valid value."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_RUN_TIME 00120 >", data)
    assert data.channels[1].batt_run_time == 120


def test_parse_rep_tx_batt_mins():
    """Test parsing TX_BATT_MINS as alternative run time command."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 TX_BATT_MINS 00125 >", data)
    assert data.channels[1].batt_run_time == 125


def test_parse_rep_chan_name():
    """Test parsing channel name response (padded with spaces)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 CHAN_NAME {Pastor                         } >", data)
    assert data.channels[1].chan_name == "Pastor"


def test_parse_rep_tx_model():
    """Test parsing transmitter model response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 2 TX_MODEL SLXD2 >", data)
    assert data.channels[2].tx_model == "SLXD2"


def test_parse_rep_frequency():
    """Test parsing frequency response (6-digit format = xxx.yyy MHz)."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 FREQUENCY 470125 >", data)
    assert data.channels[1].frequency == "470125"


def test_parse_rep_rf_int_det():
    """Test parsing RF interference detection response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 RF_INT_DET NONE >", data)
    assert data.channels[1].rf_int_det == "NONE"


def test_parse_rep_rf_int_detected():
    """Test parsing RF interference when detected."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 RF_INT_DET DETECTED >", data)
    assert data.channels[1].rf_int_det == "DETECTED"


def test_parse_rep_audio_gain():
    """Test parsing audio gain response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 AUDIO_GAIN 030 >", data)
    assert data.channels[1].audio_gain == 30


def test_parse_rep_audio_mute():
    """Test parsing audio mute response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 AUDIO_MUTE OFF >", data)
    assert data.channels[1].audio_mute == "OFF"


def test_parse_rep_group_channel():
    """Test parsing group/channel response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 GROUP_CHANNEL 01,05 >", data)
    assert data.channels[1].group_channel == "01,05"


def test_parse_rep_batt_type():
    """Test parsing battery type response."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_TYPE LION >", data)
    assert data.channels[1].batt_type == "LION"


def test_parse_sample():
    """Test parsing a SAMPLE line with audio peak, RMS, and RF level."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< SAMPLE 1 045 038 012 >", data)
    assert data.channels[1].audio_level_peak == 45
    assert data.channels[1].audio_level_rms == 38
    assert data.channels[1].rf_level == 12


def test_parse_multiple_channels():
    """Test parsing responses for multiple channels."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP 1 BATT_BARS 005 >", data)
    client._parse_response("< REP 2 BATT_BARS 003 >", data)
    assert data.channels[1].batt_bars == 5
    assert data.channels[2].batt_bars == 3


def test_parse_device_level_rep_no_channel():
    """Test parsing device-level REP without channel number."""
    client = ShureClient("192.168.1.100")
    data = ReceiverData()
    client._parse_response("< REP MODEL {SLXD4D} >", data)
    assert data.device.model == "SLXD4D"


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


def test_parse_int_unknown_sentinel():
    """Test _parse_int returns None for the 255 unknown sentinel."""
    assert _parse_int("255") is None


def test_parse_int_invalid():
    """Test _parse_int with invalid values."""
    assert _parse_int("abc") is None
    assert _parse_int("") is None
