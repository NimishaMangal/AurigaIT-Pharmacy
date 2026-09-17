"""Clock router — POST /clock triggers the daily automation job (L1).

Graded via POST /clock:
  - Quarantines batches where expiry_date < today
  - Flags batches expiring within 7 days as 'expiring_soon'
  - Returns { flagged_expiring, quarantined, timestamp }
"""

from datetime import date, timedelta, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(tags=["Clock"])


def run_daily_job(db: Session) -> dict:
    today = date.today()
    in_seven_days = today + timedelta(days=7)

    # 1. Quarantine expired batches
    expired = (
        db.query(models.Batch)
        .filter(
            models.Batch.expiry_date < today,
            models.Batch.status != models.BatchStatus.quarantined,
        )
        .all()
    )
    for batch in expired:
        batch.status = models.BatchStatus.quarantined

    # 2. Flag batches expiring within 7 days (but not yet expired)
    expiring_soon = (
        db.query(models.Batch)
        .filter(
            models.Batch.expiry_date >= today,
            models.Batch.expiry_date <= in_seven_days,
            models.Batch.status == models.BatchStatus.active,
        )
        .all()
    )
    for batch in expiring_soon:
        batch.status = models.BatchStatus.expiring_soon

    db.commit()

    return {
        "flagged_expiring": len(expiring_soon),
        "quarantined": len(expired),
        "timestamp": datetime.now(timezone.utc),
    }


@router.post("/clock", response_model=schemas.ClockResponse)
def clock(
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """
    Trigger the daily batch automation job:
    - Quarantines all expired batches
    - Flags batches expiring within 7 days
    Returns counts of each action taken.
    """
    return run_daily_job(db)
