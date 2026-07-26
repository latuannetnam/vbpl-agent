"""canonical_vbpl_schema

Revision ID: 20260726_01
Revises: 
Create Date: 2026-07-26 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
from vbpl_kb.db_models import Base

revision: str = "20260726_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
