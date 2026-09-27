"""Query a HomeKit accessory whose mDNS responder only answers legacy unicast queries.

Some accessories (e.g. Hunter SIMPLEconnect fans on Ayla/Realtek modules) never multicast
their _hap._tcp records and ignore standard (QM) queries. They do answer a query sent from an
ephemeral port directly to them. This module has no Home Assistant dependencies.
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass

from zeroconf import DNSIncoming, DNSOutgoing, DNSQuestion, ServiceInfo
from zeroconf.const import _CLASS_IN, _FLAGS_QR_QUERY, _TYPE_PTR

HAP_TYPE = "_hap._tcp.local."
MDNS_PORT = 5353


@dataclass(frozen=True)
class HapRecord:
    name: str
    server: str
    port: int
    properties: bytes
    address: str

    def to_service_info(self) -> ServiceInfo:
        return ServiceInfo(
            HAP_TYPE,
            self.name,
            addresses=[socket.inet_aton(self.address)],
            port=self.port,
            server=self.server,
            properties=self.properties,
        )


class _QueryProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.response: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

    def datagram_received(self, data: bytes, addr) -> None:
        if not self.response.done():
            self.response.set_result(data)

    def error_received(self, exc: Exception) -> None:
        if not self.response.done():
            self.response.set_exception(exc)


def build_query() -> bytes:
    out = DNSOutgoing(_FLAGS_QR_QUERY, multicast=False)
    out.add_question(DNSQuestion(HAP_TYPE, _TYPE_PTR, _CLASS_IN))
    return out.packets()[0]


def parse_response(data: bytes, address: str) -> HapRecord | None:
    records = DNSIncoming(data).answers()
    ptr = next((r for r in records if r.type == _TYPE_PTR and r.name == HAP_TYPE), None)
    if ptr is None:
        return None
    name = ptr.alias
    srv = next((r for r in records if r.name == name and hasattr(r, "port")), None)
    txt = next((r for r in records if r.name == name and hasattr(r, "text")), None)
    if srv is None or txt is None:
        return None
    return HapRecord(name=name, server=srv.server, port=srv.port, properties=txt.text, address=address)


async def async_query(host: str, timeout: float = 3.0) -> HapRecord | None:
    """Ask the accessory at host for its _hap._tcp records via a legacy unicast query."""
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _QueryProtocol, remote_addr=(host, MDNS_PORT), family=socket.AF_INET
    )
    try:
        transport.sendto(build_query())
        data = await asyncio.wait_for(protocol.response, timeout)
    except (TimeoutError, OSError):
        return None
    finally:
        transport.close()
    return parse_response(data, host)
