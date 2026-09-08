"""integrate due-today notifications into task procedures

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-08

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROCEDURES_DIR = Path(__file__).resolve().parents[3] / "db" / "procedures"


def upgrade() -> None:
	for filename in ("sp_create_task.sql", "sp_update_task.sql"):
		op.execute((PROCEDURES_DIR / filename).read_text())


def downgrade() -> None:
	# 通知処理だけを旧状態へ戻すと、既存通知との整合性を損なうため、後方互換な定義を維持する。
	pass
