"""
User、LoginHistory ORM モデルのカラム制限（email、login_identifier の254文字制限）を検証するテスト。
"""

from app.models.login_history import LoginHistory
from app.models.user import User
from sqlalchemy import String


def test_user_email_column_uses_254_character_limit() -> None:
	"""
	User モデルの email カラムが String(254) 型で定義されていることを検証。

	条件：User.__table__.c.email の型が String で、length が 254 であること。
	"""
	column_type = User.__table__.c.email.type

	assert isinstance(column_type, String)
	assert column_type.length == 254


def test_login_history_identifier_column_uses_email_limit() -> None:
	"""
	LoginHistory モデルの login_identifier カラムが String(254) 型で定義されていることを検証。

	条件：LoginHistory.__table__.c.login_identifier の型が String で、length が 254 であること。
	"""
	column_type = LoginHistory.__table__.c.login_identifier.type

	assert isinstance(column_type, String)
	assert column_type.length == 254
