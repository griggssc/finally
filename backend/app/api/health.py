"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    """Health check for Docker/deployment."""
    return {"status": "ok"}
