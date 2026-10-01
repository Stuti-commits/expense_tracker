from app.models.user import User  # noqa: F401

# Future models (goals, partnerships, statements, transactions, merchant_overrides)
# get added here as they're built, so Base.metadata.create_all() / Alembic can see them.
from app.models.user import User  # noqa: F401
from app.models.goal import Goal  # noqa: F401
from app.models.partnership import Partnership  # noqa: F401
from app.models.statement import Statement  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.merchant_override import MerchantOverride  # noqa: F401
