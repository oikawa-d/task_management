from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from starlette.requests import Request

IpSource = Literal["direct", "trusted_xff"]


@dataclass(frozen=True)
class ClientIpInfo:
	client_ip: str
	proxy_peer_ip: str
	ip_source: IpSource


def resolve_client_ip(request: Request, trusted_proxy_cidrs: list[str]) -> ClientIpInfo:
	peer = request.client.host if request.client is not None else "unknown"
	peer_address = _parse_ip(peer)
	if peer_address is None or not _is_trusted(peer_address, trusted_proxy_cidrs):
		return ClientIpInfo(peer, peer, "direct")

	forwarded = request.headers.get("x-forwarded-for")
	if not forwarded:
		return ClientIpInfo(peer, peer, "direct")
	values = [value.strip() for value in forwarded.split(",")]
	if not values or any(not value or _parse_ip(value) is None for value in values):
		return ClientIpInfo(peer, peer, "direct")
	for value in reversed(values):
		address = _parse_ip(value)
		assert address is not None
		if not _is_trusted(address, trusted_proxy_cidrs):
			return ClientIpInfo(value, peer, "trusted_xff")
	return ClientIpInfo(peer, peer, "direct")


def _parse_ip(value: str) -> IPv4Address | IPv6Address | None:
	try:
		return ipaddress.ip_address(value)
	except ValueError:
		return None


def _is_trusted(address: IPv4Address | IPv6Address, cidrs: list[str]) -> bool:
	for cidr in cidrs:
		try:
			network = ipaddress.ip_network(cidr, strict=False)
		except ValueError:
			continue
		if address in network:
			return True
	return False
