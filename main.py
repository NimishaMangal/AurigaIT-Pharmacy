"""PharmaCare — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from database import engine, SessionLocal
import models

# Import all routers
from routers.auth_router import router as auth_router
from routers.medicines import router as medicines_router
from routers.batches import router as batches_router
from routers.dispense import router as dispense_router
from routers.clock import router as clock_router, run_daily_job
from routers.outbox import router as outbox_router
from routers.import_batches import router as import_router

# ── Create tables on startup ──────────────────────────────────────────────────
models.Base.metadata.create_all(bind=engine)

# ── APScheduler: run daily job at midnight ────────────────────────────────────
scheduler = BackgroundScheduler()


def scheduled_daily_job():
    db = SessionLocal()
    try:
        result = run_daily_job(db)
        print(f"[Scheduler] Daily job ran: {result}")
    finally:
        db.close()


scheduler.add_job(scheduled_daily_job, "cron", hour=0, minute=0, id="daily_clock")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="PharmaCare",
    description=(
        "Pharmacy stock management with FIFO dispensing, expiry automation, "
        "messy data import, and reorder alerts."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(medicines_router)
app.include_router(batches_router)
app.include_router(dispense_router)
app.include_router(clock_router)
app.include_router(outbox_router)
app.include_router(import_router)

# ── Health check (must be before static mount) ────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "PharmaCare"}

# ── Static frontend ───────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")

