from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.configs import settings
from app.core.deps import close_redis
from app.db.session import async_session_maker
from app.routers import auth_router, client_router, service_router, scheduling_router

app = FastAPI(title="Scheduling System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(client_router.router)
app.include_router(service_router.router)
app.include_router(scheduling_router.router)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_redis()


@app.get("/health")
async def health_check():
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}