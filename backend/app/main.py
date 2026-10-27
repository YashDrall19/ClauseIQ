import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import contracts, health
from app.config import get_settings
from app.database import Base, engine
from app.models import Contract
from app.services.document_service import DocumentError


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Contract Q&A Chatbot API",
    description="Contract extraction and provider-backed, grounded question answering.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unexpected_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled request failure")
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})


app.include_router(health.router)
app.include_router(contracts.router)
