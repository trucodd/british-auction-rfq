import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (register models)
from .database import Base, engine
from .events import set_main_loop
from .routers import rfqs
from .scheduler import start as start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev-only: create tables on boot. Use Alembic in production.
    Base.metadata.create_all(bind=engine)
    set_main_loop(asyncio.get_running_loop())
    start_scheduler()
    yield


app = FastAPI(title="British Auction RFQ", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rfqs.router)


@app.get("/api/health")
def health():
    return {"ok": True}