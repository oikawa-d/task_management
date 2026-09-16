from app.core.client_ip import resolve_client_ip
from starlette.requests import Request


def _request(peer: str, forwarded: str | None = None) -> Request:
	headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
	return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1)})


def test_resolve_client_ip_uses_direct_peer_for_untrusted_proxy() -> None:
	result = resolve_client_ip(_request("192.0.2.1", "198.51.100.4"), ["10.0.0.0/8"])

	assert result.client_ip == "192.0.2.1"
	assert result.proxy_peer_ip == "192.0.2.1"
	assert result.ip_source == "direct"


def test_resolve_client_ip_uses_first_untrusted_xff_from_right() -> None:
	result = resolve_client_ip(_request("10.0.0.1", "198.51.100.4, 10.0.0.2"), ["10.0.0.0/8"])

	assert result.client_ip == "198.51.100.4"
	assert result.proxy_peer_ip == "10.0.0.1"
	assert result.ip_source == "trusted_xff"


def test_resolve_client_ip_falls_back_for_invalid_xff() -> None:
	result = resolve_client_ip(_request("10.0.0.1", "198.51.100.4, invalid"), ["10.0.0.0/8"])

	assert result.client_ip == "10.0.0.1"
	assert result.ip_source == "direct"


def test_resolve_client_ip_uses_direct_peer_when_all_xff_values_are_trusted() -> None:
	result = resolve_client_ip(_request("10.0.0.1", "10.0.0.2, 10.0.0.3"), ["10.0.0.0/8"])

	assert result.client_ip == "10.0.0.1"
	assert result.ip_source == "direct"


def test_resolve_client_ip_checks_cidr_boundaries() -> None:
	trusted = resolve_client_ip(_request("10.0.0.0", "198.51.100.4"), ["10.0.0.0/30"])
	not_trusted = resolve_client_ip(_request("10.0.0.4", "198.51.100.4"), ["10.0.0.0/30"])

	assert trusted.ip_source == "trusted_xff"
	assert not_trusted.client_ip == "10.0.0.4"
	assert not_trusted.ip_source == "direct"
