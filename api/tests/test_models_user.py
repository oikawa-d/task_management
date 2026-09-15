from app.models.login_history import LoginHistory
from app.models.user import User
from sqlalchemy import String


def test_user_email_column_uses_254_character_limit() -> None:
	column_type = User.__table__.c.email.type

	assert isinstance(column_type, String)
	assert column_type.length == 254


def test_login_history_identifier_column_uses_email_limit() -> None:
	column_type = LoginHistory.__table__.c.login_identifier.type

	assert isinstance(column_type, String)
	assert column_type.length == 254
