from fastapi import FastAPI
from sqlalchemy import text

from app.db.session import async_session_maker

app = FastAPI(title="Scheduling System")


@app.get("/health")
async def health_check():
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}