from fastapi import FastAPI

from app.routers import users, statements

app = FastAPI(
    title="Expense Tracker API",
    description="Backend for the expense tracker: auth via Firebase, "
    "data via PostgreSQL. Classification + goals/partnerships routers "
    "get added here in later phases.",
    version="0.1.0",
)

app.include_router(users.router)
app.include_router(statements.router)


@app.get("/health")
def health_check():
    """Basic liveness check — no auth required. Useful for uptime monitoring."""
    return {"status": "ok"}
