"""add market_cap to positions

Revision ID: 47357b4b93e5
Revises: 282ff8c54cd5
Create Date: 2026-07-13 12:17:29.351845

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47357b4b93e5'
down_revision: Union[str, Sequence[str], None] = '282ff8c54cd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('trading_positions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('market_cap', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('trading_positions', schema=None) as batch_op:
        batch_op.drop_column('market_cap')
