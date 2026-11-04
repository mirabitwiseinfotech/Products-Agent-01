
from fastapi import FastAPI

from app.api.v1.routes import router


app = FastAPI(
    title="Shopify AI Commerce Readiness Agent",
    description=(
        "Audits Shopify product catalog data, identifies missing "
        "information, and prepares AI-generated description "
        "improvements for merchant approval."
    ),
    version="1.0.0",
)


app.include_router(
    router,
    prefix="/api/v1",
)


@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "Shopify AI Commerce Readiness Agent is running.",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
