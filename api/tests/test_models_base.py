"""
SQLAlchemy ORM のベースモデルmixin（UUID PK、タイムスタンプ）の動作を検証するテスト。
"""

import uuid
from datetime import datetime

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPkMixin
from sqlalchemy import Column, String
from sqlalchemy.orm import Mapped, mapped_column


class _SampleTimestamped(UUIDPkMixin, TimestampMixin, Base):
	"""
	テスト用モデル: UUID PK と created_at/updated_at タイムスタンプを持つテーブル。
	"""

	__tablename__ = "_sample_timestamped"

	name: Mapped[str] = mapped_column(String(50), nullable=False)


class _SampleAppendOnly(UUIDPkMixin, CreatedAtMixin, Base):
	"""
	テスト用モデル: UUID PK と created_at のみを持つテーブル（append-only）。
	"""

	__tablename__ = "_sample_append_only"

	name: Mapped[str] = mapped_column(String(50), nullable=False)


def test_uuid_pk_mixin_defines_uuid_primary_key_with_db_default() -> None:
	"""
	UUIDPkMixin が UUID を主キーとして定義し、DB default (gen_random_uuid()) を設定することを検証。

	条件：UUIDPkMixin を継承したテーブルの id カラムが、PRIMARY KEY で NOT NULL、server_default が gen_random_uuid() であること。
	"""
	column: Column = _SampleTimestamped.__table__.c.id

	assert column.primary_key is True
	assert column.nullable is False
	assert str(column.server_default.arg) == "gen_random_uuid()"


def test_created_at_mixin_defines_not_null_column_with_now_default() -> None:
	"""
	CreatedAtMixin が NOT NULL の created_at カラムを定義し、server_default を設定し、updated_at は含まないことを検証。

	条件：CreatedAtMixin を継承したテーブルの created_at カラムが NOT NULL で server_default を持ち、updated_at が定義されていないこと。
	"""
	column: Column = _SampleAppendOnly.__table__.c.created_at

	assert column.nullable is False
	assert column.server_default is not None
	assert not hasattr(_SampleAppendOnly, "updated_at")


def test_timestamp_mixin_adds_updated_at_alongside_created_at() -> None:
	"""
	TimestampMixin が created_at と updated_at（両者 NOT NULL で server_default あり）を定義することを検証。

	条件：TimestampMixin を継承したテーブルに created_at と updated_at カラムが存在し、両者が NOT NULL で server_default を持つこと。
	"""
	table = _SampleTimestamped.__table__

	assert "created_at" in table.c
	updated_at: Column = table.c.updated_at
	assert updated_at.nullable is False
	assert updated_at.server_default is not None


def test_mixins_produce_instantiable_model() -> None:
	"""
	mixin を継承したモデルが instantiable で、属性が正しく機能することを検証。

	条件：UUIDPkMixin と TimestampMixin を持つモデルをインスタンス化したとき、id が UUID 型で name が正しく保持されること。
	"""
	instance = _SampleTimestamped(id=uuid.uuid4(), name="x", created_at=datetime.now(), updated_at=datetime.now())

	assert isinstance(instance.id, uuid.UUID)
	assert instance.name == "x"
