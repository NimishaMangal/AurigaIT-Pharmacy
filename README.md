# PharmaCare — Pharmacy Stock Management System

A full-stack pharmacy inventory system with **FIFO dispensing**, expiry automation, messy data import, and reorder alerts.

---

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Setup & Run

```bash
# 1. Clone / open the project folder
cd AurigaIT

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server (tables created automatically)
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** in your browser — the landing page and dashboard load immediately.

The interactive API docs are at **http://localhost:8000/docs**.

---

## How to Debug

```bash
# Run with verbose logging
uvicorn main:app --reload --log-level debug

# Inspect the SQLite database directly
sqlite3 pharmacy.db ".tables"
sqlite3 pharmacy.db "SELECT * FROM batches ORDER BY expiry_date;"

# Check the scheduler is running
# Look for "[Scheduler] Daily job ran:" lines in the server output at midnight
```

If the server fails to start:
1. Confirm Python ≥ 3.11: `python --version`
2. Re-install deps: `pip install -r requirements.txt --force-reinstall`
3. Delete `pharmacy.db` and restart to get a clean DB

---

## API Endpoints

All protected endpoints require `Authorization: Bearer <token>`.  
Get a token via `POST /login`.

### Auth
| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/register` | Create user account | ❌ |
| `POST` | `/login` | Returns JWT access token | ❌ |

### Medicines
| Method | Path | Description | Query params |
|--------|------|-------------|-------------|
| `GET` | `/medicines` | List medicines (with in-date stock) | `search`, `sort_by`, `order`, `page`, `page_size` |
| `POST` | `/medicines` | Add a new medicine | — |
| `GET` | `/medicines/{id}` | Get single medicine with stock | — |
| `PUT` | `/medicines/{id}` | Update medicine | — |
| `DELETE` | `/medicines/{id}` | Delete medicine + all batches | — |
| `GET` | `/medicines/{id}/stock` | In-date stock count + threshold check | — |

### Batches
| Method | Path | Description | Query params |
|--------|------|-------------|-------------|
| `GET` | `/batches` | List batches | `medicine_id`, `search`, `status`, `sort_by`, `order`, `page`, `page_size` |
| `POST` | `/batches` | Add a batch | — |
| `GET` | `/batches/{id}` | Get single batch | — |
| `DELETE` | `/batches/{id}` | Delete batch | — |

### Dispensing
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/dispense` | Dispense quantity FIFO (oldest-first, skips expired/quarantined) |

**Request body:** `{ "medicine_id": 1, "quantity": 20 }`  
**Response:** dispensed count, batches used, remaining stock, reorder alert flag

### Automation (L1 — T2)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/clock` | Trigger daily job: quarantine expired, flag expiring-within-7-days |

**Response:** `{ "flagged_expiring": N, "quarantined": N, "timestamp": "..." }`

### Import (L2 — T4)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/import` | Upload messy CSV (multipart `file` field) |
| `POST` | `/import/json` | POST JSON array of raw batch objects |

**Response:** `{ "imported": N, "deduped": N, "rejected": N, "errors": [...] }`

**Handled automatically:**
- Quantity strings: `"10 units"`, `"5 tablets"` → `10`, `5`
- Mixed dates: `dd/mm/yyyy`, `yyyy-mm-dd`, `dd-mm-yyyy`
- Null medicine names / unparseable dates → rejected with reason
- Duplicate rows by `(medicine_name, batch_number, expiry_date)` → deduped

### Reorder Alerts (L3 — T1)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/outbox` | List reorder alert notifications | `delivered`, `page`, `page_size` |
| `PATCH` | `/outbox/{id}/delivered` | Mark alert as delivered |

### Misc
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Architecture

```
main.py               ← FastAPI app, scheduler, static mount
database.py           ← SQLAlchemy engine (SQLite pharmacy.db)
models.py             ← ORM: User, Medicine, Batch, Outbox
schemas.py            ← Pydantic v2 request/response models
auth.py               ← JWT + bcrypt helpers
routers/
  auth_router.py      ← /register, /login
  medicines.py        ← /medicines CRUD
  batches.py          ← /batches CRUD
  dispense.py         ← /dispense
  clock.py            ← /clock (L1)
  outbox.py           ← /outbox (L3)
  import_batches.py   ← /import (L2)
services/
  fifo.py             ← FIFO dispense logic
  notification.py     ← Reorder alert outbox writer
  import_service.py   ← Messy data parser + dedup
static/
  index.html          ← Full SPA (landing + dashboard)
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `pharma-super-secret-key-change-in-prod` | JWT signing key |
| `NOTIFICATION_SERVICE_URL` | *(empty)* | If set, POSTs reorder alerts to an external service too |

---

## Running Tests (manual smoke test)

```bash
# Register and login
curl -X POST http://localhost:8000/register -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@pharma.com","password":"secret123"}'

TOKEN=$(curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Add medicine
curl -X POST http://localhost:8000/medicines -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Paracetamol 500mg","unit":"tablets","reorder_threshold":100}'

# Add batches (one expiring soon, one future)
curl -X POST http://localhost:8000/batches -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"medicine_id":1,"batch_number":"B001","quantity_remaining":50,"expiry_date":"2026-09-20"}'

curl -X POST http://localhost:8000/batches -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"medicine_id":1,"batch_number":"B002","quantity_remaining":200,"expiry_date":"2027-06-01"}'

# Dispense (FIFO — should take from B001 first)
curl -X POST http://localhost:8000/dispense -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"medicine_id":1,"quantity":30}'

# Run clock
curl -X POST http://localhost:8000/clock -H "Authorization: Bearer $TOKEN"

# Check outbox
curl http://localhost:8000/outbox -H "Authorization: Bearer $TOKEN"
```
