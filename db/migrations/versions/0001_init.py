from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    status_enum = sa.Enum("allocated", "freed", name="allocation_status")
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capacity_m", sa.Integer(), nullable=False),
        sa.Column("used_quota", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint("ck_nodes_used_quota_nonnegative", "nodes", "used_quota >= 0")
    op.create_check_constraint(
        "ck_nodes_used_quota_not_exceed_capacity", "nodes", "used_quota <= capacity_m"
    )

    op.create_table(
        "allocations",
        sa.Column("request_id", sa.String(), primary_key=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("status", status_enum, nullable=False, server_default="allocated"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_allocations_node_status", "allocations", ["node_id", "status"])


def downgrade():
    op.drop_index("ix_allocations_node_status", table_name="allocations")
    op.drop_table("allocations")
    op.drop_table("nodes")
    status_enum = sa.Enum("allocated", "freed", name="allocation_status")
    status_enum.drop(op.get_bind(), checkfirst=True)
