"""Application factory and `plainspeak` console entry point."""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from plainspeak.ai.client import LLM, ClaudeClient
from plainspeak.api import router
from plainspeak.config import Settings, get_settings
from plainspeak.storage import CaseStore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, llm: LLM | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="PlainSpeak MVP", version="0.1.0")
    app.state.store = CaseStore(settings.cases_dir, settings.uploads_dir)
    app.state.llm = llm or ClaudeClient(settings)
    app.include_router(router)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
    return app


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=settings.port)
