"""Import router — POST /import accepts CSV upload or JSON body (L2).

Delegates parsing/deduplication to services.import_service.
"""

import csv
import io
import json
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Body
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from services.import_service import process_import
import models, schemas

router = APIRouter(tags=["Import"])


@router.post("/import", response_model=schemas.ImportReport)
async def import_batches(
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """
    Import a messy batch list from a CSV file upload.

    Handles:
    - Null/empty fields
    - Quantity strings like '10 units', '5 tablets'
    - Mixed date formats: dd/mm/yyyy and ISO yyyy-mm-dd
    - Duplicate rows (deduped by medicine+batch_number+expiry_date)

    Returns: { imported, deduped, rejected, errors }
    """
    if file is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a CSV file via multipart/form-data field 'file'.",
        )

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    rows: List[Dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        rows.append(dict(row))

    if not rows:
        return {"imported": 0, "deduped": 0, "rejected": 0, "errors": ["CSV file is empty or has no data rows"]}

    return process_import(rows, db)


@router.post("/import/json", response_model=schemas.ImportReport)
def import_batches_json(
    rows: List[Dict[str, Any]] = Body(..., description="Array of batch objects"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """
    Import a messy batch list from a JSON body array.
    Same cleaning rules as the CSV endpoint.
    """
    return process_import(rows, db)
