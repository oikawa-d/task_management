"""add login_history column comments

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-09

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMN_COMMENTS = {
	"id": "ログイン試行を一意に識別するUUID",
	"user_id": "未登録ID/メール入力時はNULL",
	"login_identifier": (
		"認証に使用した識別子。通常ログインはusername/email原文、Google OAuthは検証済みGoogle email。"
		"パスワード・OAuthのsub・トークンは記録しない"
	),
	"login_method": "ログイン方式。session / jwt / oauth_google",
	"ip_address": "信頼できるProxy情報から解決した接続元IPアドレス",
	"user_agent": "ログイン試行時のUser-Agent",
	"success": "ログイン試行の成否",
	"failure_reason": "ログイン失敗時の理由。成功時はNULL",
	"created_at": "ログイン試行を記録した日時",
}


def upgrade() -> None:
	op.execute("COMMENT ON TABLE login_history IS 'ログイン試行の監査ログ。Redis側のTTL失効とは独立して保持する'")
	for column, comment in _COLUMN_COMMENTS.items():
		op.execute(f"COMMENT ON COLUMN login_history.{column} IS '{comment}'")


def downgrade() -> None:
	for column in _COLUMN_COMMENTS:
		op.execute(f"COMMENT ON COLUMN login_history.{column} IS NULL")
	op.execute("COMMENT ON TABLE login_history IS NULL")
