"""app.core.client_ip の resolve_client_ip に対する単体テスト。

信頼済みプロキシCIDRの内側/外側・X-Forwarded-Forの正常値/不正値・境界値の各パターンで、
クライアントIP・プロキシ直近IP・IP判定根拠(ip_source)が期待通りに解決されることを検証する。
"""

from app.core.client_ip import resolve_client_ip
from starlette.requests import Request


def _request(peer: str, forwarded: str | None = None) -> Request:
	"""検証用のASGIリクエストを組み立てる。

	Args:
		peer: TCP接続の直接の送信元IP(client想定)。
		forwarded: X-Forwarded-Forヘッダーの値。Noneの場合はヘッダー自体を付与しない。

	Returns:
		resolve_client_ipの入力として使えるRequestインスタンス。
	"""
	headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
	return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1)})


def test_resolve_client_ip_uses_direct_peer_for_untrusted_proxy() -> None:
	"""直接の接続元IPが信頼済みCIDRに含まれない場合、X-Forwarded-Forを無視して直接IPを採用し、ip_sourceが'direct'になることを検証する。"""
	result = resolve_client_ip(_request("192.0.2.1", "198.51.100.4"), ["10.0.0.0/8"])

	assert result.client_ip == "192.0.2.1"
	assert result.proxy_peer_ip == "192.0.2.1"
	assert result.ip_source == "direct"


def test_resolve_client_ip_uses_first_untrusted_xff_from_right() -> None:
	"""直接の接続元IPが信頼済みCIDRに含まれる場合、X-Forwarded-Forを右から走査し最初に現れる非信頼IPをクライアントIPとして採用し、ip_sourceが'trusted_xff'になることを検証する。"""
	result = resolve_client_ip(_request("10.0.0.1", "198.51.100.4, 10.0.0.2"), ["10.0.0.0/8"])

	assert result.client_ip == "198.51.100.4"
	assert result.proxy_peer_ip == "10.0.0.1"
	assert result.ip_source == "trusted_xff"


def test_resolve_client_ip_falls_back_for_invalid_xff() -> None:
	"""信頼済みプロキシ経由でもX-Forwarded-Forに不正な値が含まれる場合は解析せず直接IPへフォールバックし、ip_sourceが'direct'になることを検証する。"""
	result = resolve_client_ip(_request("10.0.0.1", "198.51.100.4, invalid"), ["10.0.0.0/8"])

	assert result.client_ip == "10.0.0.1"
	assert result.ip_source == "direct"


def test_resolve_client_ip_uses_direct_peer_when_all_xff_values_are_trusted() -> None:
	"""X-Forwarded-Forの値が全て信頼済みCIDR内のIPで非信頼IPが見つからない場合、直接の接続元IPへフォールバックし、ip_sourceが'direct'になることを検証する。"""
	result = resolve_client_ip(_request("10.0.0.1", "10.0.0.2, 10.0.0.3"), ["10.0.0.0/8"])

	assert result.client_ip == "10.0.0.1"
	assert result.ip_source == "direct"


def test_resolve_client_ip_checks_cidr_boundaries() -> None:
	"""信頼済みCIDR(10.0.0.0/30)の境界値において、範囲内のIPはX-Forwarded-Forを信頼して'trusted_xff'に、範囲外のIPは直接IPを採用して'direct'になることを検証する。"""
	trusted = resolve_client_ip(_request("10.0.0.0", "198.51.100.4"), ["10.0.0.0/30"])
	not_trusted = resolve_client_ip(_request("10.0.0.4", "198.51.100.4"), ["10.0.0.0/30"])

	assert trusted.ip_source == "trusted_xff"
	assert not_trusted.client_ip == "10.0.0.4"
	assert not_trusted.ip_source == "direct"
