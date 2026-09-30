from fastapi import FastAPI

from app.routers import users

app = FastAPI(
    title="Expense Tracker API",
    description="Backend for the expense tracker: auth via Firebase, "
    "data via PostgreSQL. Statement parsing and classification routers "
    "get added here in later phases.",
    version="0.1.0",
)

app.include_router(users.router)


@app.get("/health")
def health_check():
    """Basic liveness check — no auth required. Useful for uptime monitoring."""
    return {"status": "ok"}
