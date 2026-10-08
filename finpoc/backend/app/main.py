import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, SessionLocal, engine
from .routers import admin, ai, auth, dashboard, exceptions, recon, reports, rules, runs
from .services import seed

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if get_settings().seed_demo_data:
            seed.seed_demo(db)
        else:
            seed.seed_users_and_rules(db)
        db.commit()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition", "X-Content-SHA256"])
for module in (auth, runs, recon, exceptions, rules, reports, ai, dashboard, admin):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
