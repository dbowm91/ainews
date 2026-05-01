from alembic import op
import sqlalchemy as sa


revision = '033_add_api_token_prefix'
down_revision = '032_add_api_tokens'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('api_tokens', sa.Column('token_prefix', sa.String(length=16), nullable=True))

    # Set existing rows' token_prefix to first 16 chars of token_hash
    op.execute("""
        UPDATE api_tokens
        SET token_prefix = SUBSTR(token_hash, 1, 16)
        WHERE token_prefix IS NULL
    """)

    op.alter_column('api_tokens', 'token_prefix', nullable=False)
    op.create_index('ix_api_tokens_token_prefix', 'api_tokens', ['token_prefix'], unique=False)


def downgrade():
    op.drop_index('ix_api_tokens_token_prefix', table_name='api_tokens')
    op.drop_column('api_tokens', 'token_prefix')
