from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hap_republisher.const import DOMAIN
from custom_components.hap_republisher.hap import HapRecord

RECORD = HapRecord(
    name="SIMPLEconnect Fan M2-b9118d._hap._tcp.local.",
    server="AC000W018529957.local.",
    port=58742,
    properties=b"\x04c#=1\x14id=E3:C8:F9:30:4F:B1\x04sf=0\x04ci=3",
    address="10.0.30.173",
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations, mock_async_zeroconf):
    yield


@pytest.fixture
def aiozc():
    zc = MagicMock()
    zc.async_register_service = AsyncMock()
    zc.async_update_service = AsyncMock()
    zc.async_unregister_service = AsyncMock()
    with patch(
        "custom_components.hap_republisher.zeroconf.async_get_async_instance",
        AsyncMock(return_value=zc),
    ):
        yield zc


async def test_config_flow_creates_entry(hass):
    with patch("custom_components.hap_republisher.config_flow.async_query", AsyncMock(return_value=RECORD)), \
         patch("custom_components.hap_republisher.async_setup_entry", AsyncMock(return_value=True)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "10.0.30.173"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SIMPLEconnect Fan M2-b9118d"
    assert result["result"].unique_id == "e3:c8:f9:30:4f:b1"


async def test_config_flow_no_answer(hass):
    with patch("custom_components.hap_republisher.config_flow.async_query", AsyncMock(return_value=None)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "10.0.30.99"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_answer"}


async def test_setup_registers_updates_and_unregisters(hass, aiozc):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "10.0.30.173"}, unique_id="e3:c8:f9:30:4f:b1")
    entry.add_to_hass(hass)
    with patch("custom_components.hap_republisher.async_query", AsyncMock(return_value=RECORD)) as query:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        aiozc.async_register_service.assert_awaited_once()
        info = aiozc.async_register_service.await_args.args[0]
        assert info.port == 58742 and info.parsed_addresses() == ["10.0.30.173"]

        await entry.runtime_data.async_poll()
        aiozc.async_update_service.assert_awaited_once()

        query.return_value = None  # accessory stops answering: keep advertising
        await entry.runtime_data.async_poll()
        aiozc.async_unregister_service.assert_not_awaited()

        assert await hass.config_entries.async_unload(entry.entry_id)
        aiozc.async_unregister_service.assert_awaited_once()
