"""全ORMモデルの共通基底クラスと、主キー・タイムスタンプ用のMixinを定義するモジュール。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
	"""全ORMモデルが継承するSQLAlchemy宣言的マッピングの基底クラス。

	Alembicのマイグレーション自動生成はこのクラスの `metadata` を参照するため、
	新規モデルは必ずこのクラス（または本モジュールのMixin経由）を継承する。
	"""


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
