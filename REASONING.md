# REASONING.md — Thought Process Behind PharmaCare

## Problem Interpretation

The brief described a neighbourhood pharmacy with a very specific operational need: **First-Expiry-First-Out (FIFO)** dispensing. The core insight is that this isn't just a CRUD app — it's a domain problem with a clear business rule (never dispense expired medicine, always use the soonest-expiring batch first). Everything else flows from getting that rule right.

I identified three layers of increasing complexity:
1. **Core**: FIFO dispensing + in-date stock count
2. **L1 (T2)**: Automated daily job — flag expiring, quarantine expired
3. **L2 (T4)**: Messy CSV import with real-world data quality issues
4. **L3 (T1)**: Integration — reorder alert when stock drops below threshold

---

## Design Decisions

### Why FastAPI + SQLite?
- FastAPI's automatic OpenAPI docs mean I can test every endpoint interactively without writing a test client
- SQLite has zero infrastructure overhead — runs in a single file, no DB server needed in Codespaces
- SQLAlchemy ORM keeps the data model clean and the queries readable

### Database Schema
I kept the schema minimal but complete:
- **Medicine** — the product catalogue, with a `reorder_threshold` field (needed for L3)
- **Batch** — every physical batch with `expiry_date`, `quantity_remaining`, and a `status` enum (`active` / `expiring_soon` / `quarantined`)
- **Outbox** — the reorder alert queue (L3)
- **User** — for JWT auth

The `status` column on `Batch` is the key design choice. Rather than computing status from dates at query time (which is fragile), the clock job explicitly sets status. This means `GET /batches?status=expiring_soon` is a simple indexed query, not a date arithmetic expression evaluated on every row.

### FIFO Implementation
The FIFO logic is in `services/fifo.py`. The query is:
```sql
SELECT * FROM batches 
WHERE medicine_id = ? 
  AND expiry_date >= TODAY
  AND status != 'quarantined'
  AND quantity_remaining > 0
ORDER BY expiry_date ASC
```
Then I iterate the results, deducting from each batch until the requested quantity is fulfilled. Multi-batch deduction cascades naturally.

Crucially, the query uses `expiry_date >= TODAY` **not** `status == 'active'` — this means even `expiring_soon` batches are dispensed correctly (they're in-date, just flagged). Only quarantined batches are excluded.

### Clock Job (L1)
`POST /clock` runs the daily automation synchronously and returns the result immediately. This makes it easy to grade (deterministic, testable). The same function is also scheduled via APScheduler to run at midnight daily.

The logic has two passes:
1. Quarantine: `expiry_date < TODAY AND status != quarantined`
2. Flag: `expiry_date BETWEEN TODAY AND TODAY+7 AND status == active`

The order matters — quarantine first, then flag, so expired batches don't get double-counted as expiring_soon.

### Messy Import (L2)
The messiest part. I broke it into two helper functions:
- `_parse_quantity(raw)`: strips trailing text (`"10 units"` → `10`), handles float strings
- `_parse_date(raw)`: tries `dd/mm/yyyy`, then ISO, then `dd-mm-yyyy`

Deduplication happens in two stages:
1. **In-memory**: a `seen` set keyed by `(medicine_name_lower, batch_number, expiry_date)` for within-batch dedup
2. **DB check**: for rows that pass in-memory dedup, check if the batch already exists in the DB

New medicines are created on-the-fly during import (using `db.flush()` to get the ID before committing).

### Reorder Alert (L3)
After every dispense, `services/notification.py` checks if current in-date stock < threshold. If so, it inserts an `Outbox` row. The grader's `GET /outbox` endpoint returns this queue paginated.

I also wired an optional `NOTIFICATION_SERVICE_URL` env var — if set, the service also POSTs the alert payload to an external endpoint. This costs nothing if unused.

### Auth
JWT with 24-hour expiry. Every protected endpoint uses `Depends(get_current_user)`. Auth is shared (one pharmacy's data, multiple users) — simpler and more realistic for a single-location pharmacy.

### Frontend
A single `static/index.html` file served via FastAPI's `StaticFiles`. This means:
- Zero build step (critical for Codespaces)
- The app and API are on the same origin (no CORS complexity in development)
- The landing page and dashboard are in the same file, hidden/shown with CSS

The SPA uses plain `fetch()` with JWT stored in `localStorage`. All tables have search, sort, and pagination hooked up.

---

## Testing Approach

### Manual API testing
1. Used the FastAPI `/docs` Swagger UI to test every endpoint in sequence
2. Added medicines, then batches with different expiry dates
3. Ran `POST /clock` and verified batch statuses changed
4. Dispensed quantities spanning multiple batches to verify FIFO cascade
5. Dispensed below the reorder threshold and verified an outbox item appeared
6. Created a test CSV with mixed date formats, "10 units" quantities, null rows, and duplicate rows, then `POST /import` and verified the report counts matched expectations

### Issues Found and Fixed

**Issue 1**: Initially the FIFO query filtered `status == 'active'`, which meant `expiring_soon` batches weren't dispensed after the clock ran.  
**Fix**: Changed filter to `expiry_date >= TODAY AND status != 'quarantined'`.

**Issue 2**: The import service was committing inside the per-row loop, causing FK constraint errors when creating new medicines before their IDs were available.  
**Fix**: Used `db.flush()` to get the medicine ID without committing, then committed once at the end.

**Issue 3**: `renderPagination` in the frontend was calling `loader.name` to construct `onclick` handlers, but arrow functions have no `.name`. Changed all loaders to named function declarations.

**Issue 4**: SQLite enum columns — SQLAlchemy's `Enum` type needed `values_callable` to emit the string values of the Python enum rather than the names.  
**Fix**: `SAEnum(BatchStatus, values_callable=lambda obj: [e.value for e in obj])`.

**Issue 5**: The `StaticFiles` mount at `/` needs to come *after* all API routes are registered, otherwise it catches all requests before the routers can handle them.  
**Fix**: Moved `app.mount(...)` to the very end of `main.py`.

---

## Trade-offs

- **SQLite vs PostgreSQL**: SQLite is perfect for a demo/assessment; for production swap the `DATABASE_URL` to postgres and remove `check_same_thread`.
- **In-process scheduler**: APScheduler runs in the same process as the API. Under load this can cause drift. Production would use Celery + Redis or a dedicated cron.
- **Single `index.html`**: Easy to deploy, but not scalable to a large codebase. A real product would use React or Vue.
- **No test suite**: Time-boxed to 2.5h. In production: pytest + httpx for the API, playwright for the UI.
