from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.local_llm_service import local_llm_service


router = APIRouter()


@router.get("/api/health")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database_status = "available"
    except Exception:
        database_status = "unavailable"
    model_available = await local_llm_service.is_available()
    return {
        "status": "ok" if database_status == "available" else "degraded",
        "database_status": database_status,
        "ai_provider_available": model_available,
    }
