"""Re-advertise HomeKit accessories whose mDNS responder never multicasts.

Polls the accessory with a legacy unicast query and publishes its _hap._tcp record on Home
Assistant's shared zeroconf instance, so homekit_controller (and mDNS proxies such as the
UniFi gateway's) can see it.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from zeroconf import ServiceInfo

from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .hap import HapRecord, async_query

_LOGGER = logging.getLogger(__name__)


class Republisher:
    def __init__(self, hass: HomeAssistant, host: str) -> None:
        self.hass = hass
        self.host = host
        self._record: HapRecord | None = None
        self._info: ServiceInfo | None = None
        self._unreachable = False

    async def async_poll(self, _now=None) -> None:
        record = await async_query(self.host)
        if record is None:
            if not self._unreachable:
                _LOGGER.warning("No mDNS answer from %s; keeping last advertised record", self.host)
                self._unreachable = True
            return
        if self._unreachable:
            _LOGGER.info("%s is answering again", self.host)
            self._unreachable = False

        aiozc = await zeroconf.async_get_async_instance(self.hass)
        info = record.to_service_info()
        if self._info is None:
            await aiozc.async_register_service(info, cooperating_responders=True, strict=False)
            _LOGGER.info("Advertising %s at %s:%s", record.name, record.address, record.port)
        else:
            # Re-announce every poll: listeners (and mDNS proxies) only learn from multicast,
            # and the SRV/A records carry a short TTL.
            await aiozc.async_update_service(info)
            if record != self._record:
                _LOGGER.info("Updated %s: port=%s txt=%s", record.name, record.port, record.properties)
        self._record, self._info = record, info

    async def async_stop(self) -> None:
        if self._info is not None:
            aiozc = await zeroconf.async_get_async_instance(self.hass)
            await aiozc.async_unregister_service(self._info)
            self._info = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    republisher = Republisher(hass, entry.data[CONF_HOST])
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    await republisher.async_poll()
    entry.async_on_unload(
        async_track_time_interval(hass, republisher.async_poll, timedelta(seconds=interval))
    )
    entry.async_on_unload(republisher.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.runtime_data = republisher
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
