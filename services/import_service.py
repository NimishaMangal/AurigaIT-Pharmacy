"""Messy batch import service (L2).

Accepts a list of raw row dicts (from CSV or JSON) and:
  - Strips "10 units" → 10
  - Parses dd/mm/yyyy and ISO dates
  - Rejects rows with null medicine name, unparseable date, or non-positive qty
  - Deduplicates by (medicine_name, batch_number, expiry_date)
  - Creates Medicine records on-the-fly if they don't exist
  - Returns { imported, deduped, rejected, errors }
"""

import re
from datetime import date, datetime
from typing import List, Dict, Any, Tuple

from sqlalchemy.orm import Session

import models


def _parse_quantity(raw) -> Tuple[int, str]:
    """Return (int_qty, error_string_or_empty)."""
    if raw is None or str(raw).strip() == "":
        return 0, "quantity is null/empty"
    s = str(raw).strip().lower()
    # strip trailing non-numeric words: "10 units", "5 tablets", etc.
    s = re.sub(r"[a-z\s]+$", "", s).strip()
    try:
        qty = int(float(s))
        if qty <= 0:
            return 0, f"quantity '{raw}' is not positive"
        return qty, ""
    except ValueError:
        return 0, f"cannot parse quantity '{raw}'"


def _parse_date(raw) -> Tuple[date | None, str]:
    """Return (date_obj, error_string_or_empty)."""
    if raw is None or str(raw).strip() == "":
        return None, "expiry_date is null/empty"
    s = str(raw).strip()
    # Try dd/mm/yyyy
    try:
        return datetime.strptime(s, "%d/%m/%Y").date(), ""
    except ValueError:
        pass
    # Try ISO 8601 yyyy-mm-dd
    try:
        return date.fromisoformat(s), ""
    except ValueError:
        pass
    # Try dd-mm-yyyy
    try:
        return datetime.strptime(s, "%d-%m-%Y").date(), ""
    except ValueError:
        pass
    return None, f"cannot parse date '{raw}'"


def process_import(rows: List[Dict[str, Any]], db: Session) -> dict:
    """
    Process a list of raw row dicts and insert valid deduplicated batches.
    Returns { imported, deduped, rejected, errors }.
    """
    imported = 0
    deduped = 0
    rejected = 0
    errors: List[str] = []
    seen: set = set()  # (medicine_name_lower, batch_number, expiry_date)

    for idx, row in enumerate(rows, start=1):
        label = f"Row {idx}"

        # Normalise keys to lowercase
        row = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}

        # ── Medicine name ──────────────────────────────────────────────────
        med_name = row.get("medicine_name") or row.get("medicine") or row.get("name")
        if not med_name or str(med_name).strip() == "":
            rejected += 1
            errors.append(f"{label}: medicine name is null/empty")
            continue
        med_name = str(med_name).strip()

        # ── Batch number ──────────────────────────────────────────────────
        batch_num = str(row.get("batch_number") or row.get("batch") or "UNKNOWN").strip()

        # ── Quantity ──────────────────────────────────────────────────────
        qty_raw = row.get("quantity") or row.get("quantity_remaining") or row.get("qty")
        qty, qty_err = _parse_quantity(qty_raw)
        if qty_err:
            rejected += 1
            errors.append(f"{label} ({med_name}): {qty_err}")
            continue

        # ── Expiry date ───────────────────────────────────────────────────
        exp_raw = row.get("expiry_date") or row.get("expiry") or row.get("exp_date")
        exp_date, date_err = _parse_date(exp_raw)
        if date_err:
            rejected += 1
            errors.append(f"{label} ({med_name}): {date_err}")
            continue

        # ── Deduplication ─────────────────────────────────────────────────
        dedup_key = (med_name.lower(), batch_num, exp_date)
        if dedup_key in seen:
            deduped += 1
            continue
        seen.add(dedup_key)

        # ── Also check DB for existing batch ─────────────────────────────
        medicine = (
            db.query(models.Medicine)
            .filter(models.Medicine.name.ilike(med_name))
            .first()
        )
        if medicine is None:
            medicine = models.Medicine(name=med_name)
            db.add(medicine)
            db.flush()  # get medicine.id

        existing_batch = (
            db.query(models.Batch)
            .filter(
                models.Batch.medicine_id == medicine.id,
                models.Batch.batch_number == batch_num,
                models.Batch.expiry_date == exp_date,
            )
            .first()
        )
        if existing_batch:
            deduped += 1
            continue

        # ── Insert ────────────────────────────────────────────────────────
        status = models.BatchStatus.active
        if exp_date < date.today():
            status = models.BatchStatus.quarantined

        batch = models.Batch(
            medicine_id=medicine.id,
            batch_number=batch_num,
            quantity_remaining=qty,
            expiry_date=exp_date,
            status=status,
        )
        db.add(batch)
        imported += 1

    db.commit()
    return {"imported": imported, "deduped": deduped, "rejected": rejected, "errors": errors}
