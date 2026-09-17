"""FIFO (First-Expiry-First-Out) dispense service."""

from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

import models
from services.notification import maybe_send_reorder_alert


def dispense_medicine(medicine_id: int, quantity: int, db: Session) -> dict:
    """
    Dispense `quantity` units of a medicine using FIFO (earliest expiry first).
    Expired and quarantined batches are skipped.
    Raises HTTP 422 if insufficient in-date stock.
    """
    today = date.today()

    medicine = db.get(models.Medicine, medicine_id)
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")

    if quantity <= 0:
        raise HTTPException(status_code=422, detail="Quantity must be positive")

    # Fetch eligible batches ordered by expiry_date ASC (FIFO)
    eligible = (
        db.query(models.Batch)
        .filter(
            models.Batch.medicine_id == medicine_id,
            models.Batch.expiry_date >= today,
            models.Batch.status != models.BatchStatus.quarantined,
            models.Batch.quantity_remaining > 0,
        )
        .order_by(models.Batch.expiry_date.asc())
        .all()
    )

    total_available = sum(b.quantity_remaining for b in eligible)
    if total_available < quantity:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient in-date stock. Available: {total_available}, Requested: {quantity}",
        )

    remaining_to_dispense = quantity
    batches_used = []

    for batch in eligible:
        if remaining_to_dispense <= 0:
            break
        take = min(batch.quantity_remaining, remaining_to_dispense)
        batch.quantity_remaining -= take
        remaining_to_dispense -= take
        batches_used.append({
            "batch_id": batch.id,
            "batch_number": batch.batch_number,
            "expiry_date": str(batch.expiry_date),
            "dispensed": take,
        })

    db.commit()

    # Recalculate remaining in-date stock after dispense
    remaining_stock = (
        db.query(models.Batch)
        .filter(
            models.Batch.medicine_id == medicine_id,
            models.Batch.expiry_date >= today,
            models.Batch.status != models.BatchStatus.quarantined,
        )
        .all()
    )
    current_stock = sum(b.quantity_remaining for b in remaining_stock)

    # L3: fire reorder alert if stock dropped below threshold
    reorder_alert = maybe_send_reorder_alert(medicine, current_stock, db)

    return {
        "medicine_id": medicine_id,
        "medicine_name": medicine.name,
        "dispensed": quantity,
        "batches_used": batches_used,
        "remaining_stock": current_stock,
        "reorder_alert": reorder_alert,
    }
