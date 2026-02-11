"""Rav Itamar — main FastAPI application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from app.core.database import init_db
from app.api import pdfs, chat, profile, restudy


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Rav Itamar",
    description="KB-grounded mentor with RAG pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all for v1 (no auth)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(pdfs.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(restudy.router, prefix="/api")

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
static_dir = os.path.join(frontend_dir, "static")
templates_dir = os.path.join(frontend_dir, "templates")

if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_spa():
    """Serve the SPA index.html."""
    index_path = os.path.join(templates_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "Rav Itamar API is running. Frontend not found."}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rav-itamar"}
