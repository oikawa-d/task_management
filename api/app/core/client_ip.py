"""信頼済みプロキシ経由のX-Forwarded-Forを考慮してクライアントIPを解決するモジュール。"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from starlette.requests import Request

IpSource = Literal["direct", "trusted_xff"]


@dataclass(frozen=True)
class ClientIpInfo:
	"""クライアントIPの解決結果を表す不変データ。

	Attributes:
		client_ip: レート制限・監査ログ等で利用する、実クライアントとみなすIPアドレス。
		proxy_peer_ip: TCP接続の直接の相手（プロキシ経由時はプロキシのIP）。
		ip_source: `client_ip`の由来。直接接続なら"direct"、信頼済みプロキシの
			X-Forwarded-Forから採用した場合は"trusted_xff"。
	"""

	client_ip: str
	proxy_peer_ip: str
	ip_source: IpSource


def resolve_client_ip(request: Request, trusted_proxy_cidrs: list[str]) -> ClientIpInfo:
	"""リクエストの接続元IPと、信頼済みプロキシ設定からクライアントIPを解決する。

	直接の接続元(`request.client.host`)が`trusted_proxy_cidrs`に含まれない場合は
	そのIPをそのまま採用する。信頼済みプロキシからの接続の場合のみ、
	X-Forwarded-Forヘッダを末尾（最も内側）から辿り、信頼済みプロキシでない
	最初の値をクライアントIPとして採用する。ヘッダが欠落・不正な形式の場合は
	直接の接続元IPにフォールバックする（なりすまし防止）。

	Args:
		request: 解決対象のHTTPリクエスト。
		trusted_proxy_cidrs: 信頼するプロキシのCIDR一覧（`BackendSettings.trusted_proxy_cidrs`）。

	Returns:
		解決済みのクライアントIP・直接接続元IP・解決方法をまとめた`ClientIpInfo`。
	"""
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
	"""文字列をIPアドレスへ変換する。変換できない場合はNoneを返す。"""
	try:
		return ipaddress.ip_address(value)
	except ValueError:
		return None


def _is_trusted(address: IPv4Address | IPv6Address, cidrs: list[str]) -> bool:
	"""指定IPが、渡されたCIDRのいずれかに含まれるかを判定する。不正なCIDRは無視する。"""
	for cidr in cidrs:
		try:
			network = ipaddress.ip_network(cidr, strict=False)
		except ValueError:
			continue
		if address in network:
			return True
	return False
