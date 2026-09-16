import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPkMixin

if TYPE_CHECKING:
	from app.models.user import User


class OAuthAccount(UUIDPkMixin, CreatedAtMixin, Base):
	__tablename__ = "oauth_accounts"

	user_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
	)
	provider: Mapped[str] = mapped_column(String(20), nullable=False)
	provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)
	provider_email: Mapped[str | None] = mapped_column(Text, nullable=True)

	user: Mapped["User"] = relationship(back_populates="oauth_accounts", lazy="joined")

	__table_args__ = (
		CheckConstraint("provider IN ('google')", name="ck_oauth_accounts_provider"),
		UniqueConstraint("provider", "provider_user_id", name="uq_oauth_accounts_provider_provider_user_id"),
		Index("ix_oauth_accounts_user_id", "user_id"),
	)
