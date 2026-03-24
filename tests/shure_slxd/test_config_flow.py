"""Tests for the Shure SLX-D config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

import custom_components.shure_slxd.config_flow  # noqa: F401
from custom_components.shure_slxd.const import CONF_HOST, CONF_NUM_CHANNELS, DOMAIN

PATCH_TARGET = "custom_components.shure_slxd.config_flow.ShureClient"


@pytest.fixture
def mock_client_success():
    """Mock a successful Shure client connection."""
    with patch(PATCH_TARGET) as mock_cls:
        client = AsyncMock()
        client.test_connection.return_value = {
            "model": "SLXD4D",
            "fw_ver": "2.3.15",
            "device_id": "00A0AE123456",
        }
        mock_cls.return_value = client
        yield client


@pytest.fixture
def mock_client_connection_error():
    """Mock a failed Shure client connection."""
    with patch(PATCH_TARGET) as mock_cls:
        client = AsyncMock()
        client.test_connection.side_effect = ConnectionError("Connection refused")
        mock_cls.return_value = client
        yield client


@pytest.fixture
def mock_setup_entry():
    """Mock async_setup_entry."""
    with patch(
        "custom_components.shure_slxd.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


async def test_config_flow_success(hass: HomeAssistant, mock_client_success, mock_setup_entry) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.168.1.100",
            CONF_NUM_CHANNELS: 2,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Shure SLXD4D"
    assert result["data"][CONF_HOST] == "192.168.1.100"
    assert result["data"][CONF_NUM_CHANNELS] == 2


async def test_config_flow_connection_error(hass: HomeAssistant, mock_client_connection_error) -> None:
    """Test config flow with connection error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.168.1.100",
            CONF_NUM_CHANNELS: 2,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_duplicate_entry(hass: HomeAssistant, mock_client_success, mock_setup_entry) -> None:
    """Test config flow aborts on duplicate entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.168.1.100",
            CONF_NUM_CHANNELS: 2,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # Try to create second entry with same host
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.168.1.100",
            CONF_NUM_CHANNELS: 1,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_config_flow_single_channel(hass: HomeAssistant, mock_client_success, mock_setup_entry) -> None:
    """Test config flow with single channel receiver."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "10.0.0.50",
            CONF_NUM_CHANNELS: 1,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NUM_CHANNELS] == 1
