from fastapi import FastAPI

from app.routers import users, statements, transactions, goals

app = FastAPI(
    title="Expense Tracker API",
    description="Backend for the expense tracker: auth via Firebase, "
    "data via PostgreSQL. Dashboard endpoints get added here in a "
    "later phase.",
    version="0.1.0",
)

app.include_router(users.router)
app.include_router(statements.router)
app.include_router(transactions.router)
app.include_router(goals.router)


@app.get("/health")
def health_check():
    """Basic liveness check — no auth required. Useful for uptime monitoring."""
    return {"status": "ok"}
