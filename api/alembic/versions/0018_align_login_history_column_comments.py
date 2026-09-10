"""align login_history column comments with the detailed design

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.execute("COMMENT ON COLUMN login_history.id IS NULL")


def downgrade() -> None:
	op.execute("COMMENT ON COLUMN login_history.id IS 'ログイン試行を一意に識別するUUID'")
