import uuid
from datetime import datetime

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UUIDPkMixin
from sqlalchemy import Column, String
from sqlalchemy.orm import Mapped, mapped_column


class _SampleTimestamped(UUIDPkMixin, TimestampMixin, Base):
	__tablename__ = "_sample_timestamped"

	name: Mapped[str] = mapped_column(String(50), nullable=False)


class _SampleAppendOnly(UUIDPkMixin, CreatedAtMixin, Base):
	__tablename__ = "_sample_append_only"

	name: Mapped[str] = mapped_column(String(50), nullable=False)


def test_uuid_pk_mixin_defines_uuid_primary_key_with_db_default() -> None:
	column: Column = _SampleTimestamped.__table__.c.id

	assert column.primary_key is True
	assert column.nullable is False
	assert str(column.server_default.arg) == "gen_random_uuid()"


def test_created_at_mixin_defines_not_null_column_with_now_default() -> None:
	column: Column = _SampleAppendOnly.__table__.c.created_at

	assert column.nullable is False
	assert column.server_default is not None
	assert not hasattr(_SampleAppendOnly, "updated_at")


def test_timestamp_mixin_adds_updated_at_alongside_created_at() -> None:
	table = _SampleTimestamped.__table__

	assert "created_at" in table.c
	updated_at: Column = table.c.updated_at
	assert updated_at.nullable is False
	assert updated_at.server_default is not None


def test_mixins_produce_instantiable_model() -> None:
	instance = _SampleTimestamped(id=uuid.uuid4(), name="x", created_at=datetime.now(), updated_at=datetime.now())

	assert isinstance(instance.id, uuid.UUID)
	assert instance.name == "x"
