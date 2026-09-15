from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.login_history import LoginHistory
	from app.models.oauth_account import OAuthAccount


class User(UUIDPkMixin, TimestampMixin, Base):
	__tablename__ = "users"

	username: Mapped[str] = mapped_column(String(50), nullable=False)
	email: Mapped[str] = mapped_column(String(50), nullable=False)
	password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
	last_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
	first_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
	last_name_kana: Mapped[str | None] = mapped_column(String(30), nullable=True)
	first_name_kana: Mapped[str | None] = mapped_column(String(30), nullable=True)
	birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
	role: Mapped[str] = mapped_column(String(10), nullable=False, server_default="member")
	is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
	email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

	oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
		back_populates="user", cascade="all, delete-orphan", lazy="selectin"
	)
	login_histories: Mapped[list["LoginHistory"]] = relationship(back_populates="user", lazy="noload")

	__table_args__ = (
		CheckConstraint("role IN ('member', 'admin')", name="ck_users_role"),
		CheckConstraint(r"username ~ '^[A-Za-z0-9_-]+$'", name="ck_users_username_format"),
		CheckConstraint(
			r"email ~ '^[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
			name="ck_users_email_format",
		),
		CheckConstraint(
			r"(last_name_kana IS NULL OR last_name_kana ~ '^[ぁ-んァ-ヶー0-9]+$')"
			r" AND (first_name_kana IS NULL OR first_name_kana ~ '^[ぁ-んァ-ヶー0-9]+$')",
			name="ck_users_kana_format",
		),
	)
