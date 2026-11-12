"""add imputed to quality_flag check constraint

Revision ID: a1c4e7f9b210
Revises: 6fba427fd828
Create Date: 2026-11-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e7f9b210'
down_revision: Union[str, None] = '6fba427fd828'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_FLAGS = ('valid', 'missing', 'duplicate', 'out_of_range', 'abnormal_event')
NEW_FLAGS = OLD_FLAGS + ('imputed',)


def upgrade() -> None:
    op.drop_constraint("ck_reading_quality_flag_valid", "readings", type_="check")
    op.create_check_constraint(
        "ck_reading_quality_flag_valid",
        "readings",
        f"quality_flag IN {NEW_FLAGS}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_reading_quality_flag_valid", "readings", type_="check")
    op.create_check_constraint(
        "ck_reading_quality_flag_valid",
        "readings",
        f"quality_flag IN {OLD_FLAGS}",
    )
