from fastapi import APIRouter
from prometheus_client import generate_latest

router = APIRouter()


@router.get("/health")
async def health():
    pass


@router.get("/metrics")
async def metrics():
    return generate_latest()
