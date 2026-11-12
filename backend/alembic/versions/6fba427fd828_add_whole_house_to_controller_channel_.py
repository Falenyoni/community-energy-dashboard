"""add whole_house to controller_channel check constraint

Revision ID: 6fba427fd828
Revises: 75ca82b27a21
Create Date: 2026-11-02 11:46:09.789204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6fba427fd828'
down_revision: Union[str, None] = '75ca82b27a21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_CHANNELS = ('geyser', 'fridge', 'lighting', 'plugs', 'cooking', 'background')
NEW_CHANNELS = OLD_CHANNELS + ('whole_house',)


def upgrade() -> None:
    op.drop_constraint(
        "ck_channel_controller_channel_valid", "smart_controller_channels", type_="check"
    )
    op.create_check_constraint(
        "ck_channel_controller_channel_valid",
        "smart_controller_channels",
        f"controller_channel IN {NEW_CHANNELS}",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_channel_controller_channel_valid", "smart_controller_channels", type_="check"
    )
    op.create_check_constraint(
        "ck_channel_controller_channel_valid",
        "smart_controller_channels",
        f"controller_channel IN {OLD_CHANNELS}",
    )
