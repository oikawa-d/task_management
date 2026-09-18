"""メール認証・パスワードリセットの本文レンダリングとSMTP送信。"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import get_backend_settings

logger = logging.getLogger("app.mail")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "mail"


@lru_cache
def _get_jinja_env() -> Environment:
	"""メールテンプレート用のJinja2環境を生成し、プロセス内でキャッシュする。

	HTMLテンプレートに対してはautoescapeを有効化し、XSSにつながる
	未エスケープ出力を防ぐ。

	Returns:
		Environment: メールテンプレートディレクトリを参照するJinja2環境。
	"""
	return Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=select_autoescape(["html"]))


def _render(template_prefix: str, context: dict[str, object]) -> tuple[str, str]:
	"""指定したテンプレート名接頭辞のHTML版・テキスト版本文を描画する。

	Args:
		template_prefix: `templates/mail/`配下のテンプレートファイル名接頭辞
			（`{prefix}.html` / `{prefix}.txt`を読み込む）。
		context: テンプレートへ渡す変数群。

	Returns:
		tuple[str, str]: (HTML本文, テキスト本文)。
	"""
	env = _get_jinja_env()
	html_body = env.get_template(f"{template_prefix}.html").render(**context)
	text_body = env.get_template(f"{template_prefix}.txt").render(**context)
	return html_body, text_body


async def _send_mail(to: str, subject: str, html_body: str, text_body: str) -> None:
	"""SMTP経由でHTML/テキストのマルチパートメールを送信する。

	送信失敗時は例外を送出せずログにエラーを記録するのみとする。これは
	呼び出し元がBackgroundTasks経由であり、メール送信失敗によって
	本来のAPIレスポンス（登録・リセット申請等）を失敗させないための設計。
	送信失敗ログにはトークンの平文・ハッシュを含めない。

	Args:
		to: 送信先メールアドレス。
		subject: メール件名。
		html_body: HTML形式の本文。
		text_body: プレーンテキスト形式の本文。

	Returns:
		None: 送信成否にかかわらず戻り値はない。
	"""
	settings = get_backend_settings()
	message = EmailMessage()
	message["From"] = settings.mail_from
	message["To"] = to
	message["Subject"] = subject
	message.set_content(text_body)
	message.add_alternative(html_body, subtype="html")

	try:
		await aiosmtplib.send(
			message,
			hostname=settings.smtp_host,
			port=settings.smtp_port,
			username=settings.smtp_user or None,
			password=settings.smtp_password or None,
			start_tls=settings.smtp_use_tls,
		)
	except Exception:
		# 送信失敗はログのみに留め、呼び出し元（BackgroundTasks）へは伝播させない。
		# トークン平文・ハッシュはログに出力しない。
		logger.error("failed to send mail")


async def send_email_verification_mail(to: str, token: str, expires_hours: int) -> None:
	"""メールアドレス確認用のリンクを含むメールを送信する。

	トークンはURLフラグメント（`#token=`）に埋め込み、サーバーログや
	リファラへ平文が渡らないようにする。

	Args:
		to: 送信先メールアドレス。
		token: メール認証用トークン（平文）。
		expires_hours: トークンの有効期限（時間）。文面表示用。

	Returns:
		None: 送信失敗時も例外は送出しない（`_send_mail`参照）。
	"""
	settings = get_backend_settings()
	verify_url = f"{settings.frontend_base_url}/verify-email#token={token}"
	html_body, text_body = _render("email_verification", {"verify_url": verify_url, "expires_hours": expires_hours})
	await _send_mail(to, "メールアドレスのご確認", html_body, text_body)


async def send_password_reset_mail(to: str, token: str, expires_minutes: int) -> None:
	"""パスワード再設定用のリンクを含むメールを送信する。

	トークンはURLフラグメント（`#token=`）に埋め込み、サーバーログや
	リファラへ平文が渡らないようにする。

	Args:
		to: 送信先メールアドレス。
		token: パスワードリセット用トークン(平文)。
		expires_minutes: トークンの有効期限（分）。文面表示用。

	Returns:
		None: 送信失敗時も例外は送出しない（`_send_mail`参照）。
	"""
	settings = get_backend_settings()
	reset_url = f"{settings.frontend_base_url}/password/reset#token={token}"
	html_body, text_body = _render("password_reset", {"reset_url": reset_url, "expires_minutes": expires_minutes})
	await _send_mail(to, "パスワード再設定のご案内", html_body, text_body)
