from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db.database import DATABASE_URL, init_db
from .services.fcm import init_fcm
from .api import auth, config, contacts, dashboard, devices, events, family_members, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    init_fcm()
    yield


app = FastAPI(
    title="Fall Detection Backend",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,    prefix="/auth",    tags=["Auth"])
app.include_router(events.router,  prefix="/events",  tags=["Events"])
app.include_router(config.router,  prefix="/config",  tags=["Config"])
app.include_router(websocket.router, prefix="/ws",    tags=["WebSocket"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(devices.router,         prefix="/devices",        tags=["Devices"])
app.include_router(family_members.router,  prefix="/family-members", tags=["Family Members"])
app.include_router(contacts.router,        prefix="/api/contacts",   tags=["Emergency Contacts"])


@app.get("/health", tags=["Health"])
async def health() -> dict:
    db_type = "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite"
    return {"status": "ok", "version": "2.1.0", "db": db_type}