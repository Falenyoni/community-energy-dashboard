from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Reading

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/reading-count")
def reading_count(db: Session = Depends(get_db)):
    count = db.query(func.count(Reading.reading_id)).scalar()
    return {"count": count}
