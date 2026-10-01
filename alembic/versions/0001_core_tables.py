"""create core tables: users, goals, partnerships, statements, transactions, merchant_overrides

Revision ID: 0001_core_tables
Revises:
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_core_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users ---------------------------------------------------------
    # id is the Firebase UID (string), not an auto-increment integer.
    # Every other table's user_id column below is String for the same reason.
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("tier_thresholds", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- goals -----------------------------------------------------------
    goal_type = postgresql.ENUM("personal", "partnership", name="goal_type",create_type=False)
    goal_period = postgresql.ENUM("weekly", "monthly", name="goal_period",create_type=False)
    goal_status = postgresql.ENUM("active", "completed", "abandoned", name="goal_status",create_type=False)
    goal_type.create(op.get_bind(), checkfirst=True)
    goal_period.create(op.get_bind(), checkfirst=True)
    goal_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("type", goal_type, nullable=False),
        sa.Column("period", goal_period, nullable=False),
        sa.Column("status", goal_status, nullable=False, server_default="active"),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])

    # --- partnerships ------------------------------------------------------
    partnership_status = postgresql.ENUM(
        "pending", "active", "completed", "declined", name="partnership_status", create_type=False
    )
    partnership_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "partnerships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_a_id", sa.String(), nullable=False),
        sa.Column("user_b_id", sa.String(), nullable=True),
        sa.Column(
            "goal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goals.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", partnership_status, nullable=False, server_default="pending"),
        sa.Column("invite_token", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_partnerships_user_a_id", "partnerships", ["user_a_id"])
    op.create_index("ix_partnerships_user_b_id", "partnerships", ["user_b_id"])
    op.create_index("ix_partnerships_invite_token", "partnerships", ["invite_token"])

    # --- statements ---------------------------------------------------------
    statement_status = postgresql.ENUM("processing", "parsed", "failed", name="statement_status",create_type=False)
    statement_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("bank_name", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("status", statement_status, nullable=False, server_default="processing"),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "file_hash", name="uq_statement_user_filehash"),
    )
    op.create_index("ix_statements_user_id", "statements", ["user_id"])

    # --- transactions -----------------------------------------------------
    tx_direction = postgresql.ENUM("debit", "credit", name="transaction_direction", create_type=False)
    tx_category = postgresql.ENUM(
        "rent", "emi", "groceries", "utilities", "food_delivery",
        "shopping", "entertainment", "transfer", "income", "other",
        name="transaction_category",
        create_type=False
    )
    tx_tier = postgresql.ENUM(
        "primary", "secondary", "tertiary", "not_applicable", name="transaction_tier", create_type=False    
    )
    tx_direction.create(op.get_bind(), checkfirst=True)
    tx_category.create(op.get_bind(), checkfirst=True)
    tx_tier.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "statement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("statements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("direction", tx_direction, nullable=False),
        sa.Column("merchant_raw", sa.String(), nullable=False),
        sa.Column("merchant_normalized", sa.String(), nullable=False),
        sa.Column("category", tx_category, nullable=False, server_default="other"),
        sa.Column("tier", tx_tier, nullable=False, server_default="not_applicable"),
        sa.Column("is_manual_override", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tx_hash", sa.String(), nullable=False),
        sa.UniqueConstraint("tx_hash", name="uq_transaction_hash"),
    )
    op.create_index("ix_transactions_user_date", "transactions", ["user_id", "date"])
    op.create_index(
        "ix_transactions_merchant_normalized", "transactions", ["merchant_normalized"]
    )

    # --- merchant_overrides -------------------------------------------------
    op.create_table(
        "merchant_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("merchant_normalized", sa.String(), nullable=False),
        sa.Column("category", tx_category, nullable=False),
        sa.Column("tier", tx_tier, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "merchant_normalized", name="uq_override_user_merchant"),
    )
    op.create_index("ix_merchant_overrides_user_id", "merchant_overrides", ["user_id"])


def downgrade() -> None:
    op.drop_table("merchant_overrides")
    op.drop_table("transactions")
    op.drop_table("statements")
    op.drop_table("partnerships")
    op.drop_table("goals")
    op.drop_table("users")

    # Enum types must be dropped explicitly in Postgres — dropping the tables
    # that used them does not drop the types themselves.
    for enum_name in [
        "goal_type", "goal_period", "goal_status",
        "partnership_status", "statement_status",
        "transaction_direction", "transaction_category", "transaction_tier",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
