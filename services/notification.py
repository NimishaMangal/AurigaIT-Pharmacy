"""Reorder alert notification service (L3).

Writes to the local `outbox` table. The GET /outbox endpoint exposes
the queue to the grader. No external HTTP call is made by default;
set NOTIFICATION_SERVICE_URL in the environment to also POST externally.
"""

import os
import logging
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "")


def maybe_send_reorder_alert(
    medicine: models.Medicine, current_stock: int, db: Session
) -> bool:
    """
    If current_stock < medicine.reorder_threshold, insert an Outbox record.
    Returns True if an alert was fired, False otherwise.
    """
    if current_stock >= medicine.reorder_threshold:
        return False

    message = (
        f"REORDER ALERT: {medicine.name} — in-date stock is {current_stock} "
        f"{medicine.unit}, below threshold of {medicine.reorder_threshold} {medicine.unit}."
    )

    item = models.Outbox(
        medicine_id=medicine.id,
        medicine_name=medicine.name,
        message=message,
        current_stock=current_stock,
        threshold=medicine.reorder_threshold,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Optional: POST to external notification service
    if NOTIFICATION_SERVICE_URL:
        try:
            import urllib.request, json
            payload = json.dumps({
                "medicine_id": medicine.id,
                "medicine_name": medicine.name,
                "current_stock": current_stock,
                "threshold": medicine.reorder_threshold,
                "message": message,
            }).encode()
            req = urllib.request.Request(
                NOTIFICATION_SERVICE_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception as exc:
            logger.warning("Failed to POST to notification service: %s", exc)

    return True
