from fastapi import FastAPI
from sqlalchemy import text

from app.db.session import async_session_maker
from app.routers import auth_router, client_router, service_router, scheduling_router

app = FastAPI(title="Scheduling System")

app.include_router(auth_router.router)
app.include_router(client_router.router)
app.include_router(service_router.router)
app.include_router(scheduling_router.router)


@app.get("/health")
async def health_check():
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}