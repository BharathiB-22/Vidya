from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="Vidya Backend")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
