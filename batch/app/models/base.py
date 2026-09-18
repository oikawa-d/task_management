"""SQLAlchemyモデルの共通基底クラスと共通カラムMixinを定義するモジュール。

主キー・作成日時・更新日時など複数テーブルで共通する列定義をMixin化し、
各モデルでの重複記述を避ける。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
	"""batchが扱う全SQLAlchemyモデルの共通基底クラス。"""

	pass


class UUIDPkMixin:
	"""UUID主キー（DB側 gen_random_uuid() 採番）を持つテーブル向けの共通カラム。"""

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)


class CreatedAtMixin:
	"""作成日時のみを持つ（追記専用）テーブル向けの共通カラム。"""

	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TimestampMixin(CreatedAtMixin):
	"""作成日時・更新日時（トリガ自動更新）を持つテーブル向けの共通カラム。"""

	updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
