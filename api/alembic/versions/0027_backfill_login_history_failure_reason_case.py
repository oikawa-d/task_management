"""backfill login_history.failure_reason to lowercase snake_case

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-15

downgradeについて:
本マイグレーションが変換した行のうち、元の値が大文字だったものを特定する手がかりは
残っていない（変換前の値を別カラムに退避していないため）。そのため downgrade は
値の復元を行わず no-op とする。

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.execute(
		"UPDATE login_history SET failure_reason = lower(failure_reason) "
		"WHERE failure_reason <> lower(failure_reason)"
	)


def downgrade() -> None:
	# 変換前の値（大文字だったかどうか）を特定する手段が無いため、意図的に no-op とする。
	pass
