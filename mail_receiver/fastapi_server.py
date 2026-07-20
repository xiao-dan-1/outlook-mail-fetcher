"""FastAPI backend for Outlook Mail Fetcher with WebSocket progress updates."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .accounts import AccountFormatError, filter_accounts_by_email, load_accounts, parse_accounts
from .application import (
    MAX_ACCOUNT_FETCH_WORKERS,
    AccountFetchOptions,
    BatchFetchService,
)
from .imap_client import DEFAULT_IMAP_HOST, DEFAULT_IMAP_PORT, DEFAULT_IMAP_TIMEOUT, fetch_messages
from .mail_fetching import OutlookAccountMailFetcher
from .oauth import DEFAULT_SCOPE, TOKEN_ENDPOINT
from .output import visible_text
from .web import WebConfig, resolve_accounts, payload_int, payload_bool

LOGGER = logging.getLogger(__name__)

# WebSocket connection manager for progress updates
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_progress(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        try:
            await websocket.send_json({"type": "progress", **data})
        except Exception:
            self.disconnect(websocket)


manager = ConnectionManager()

# Store for active fetch tasks
active_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    LOGGER.info("FastAPI server starting up...")
    yield
    # Shutdown
    LOGGER.info("FastAPI server shutting down...")
    for task in active_tasks.values():
        task.cancel()


app = FastAPI(
    title="Outlook Mail Fetcher",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (serve the built frontend)
app.mount("/static", StaticFiles(directory="frontend/dist", html=True), name="static")


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    """Get application configuration."""
    return {
        "version": __version__,
        "account_file": None,
        "defaults": {
            "mailbox": "INBOX",
            "limit": 1,
            "imap_host": DEFAULT_IMAP_HOST,
            "imap_port": DEFAULT_IMAP_PORT,
            "imap_timeout": DEFAULT_IMAP_TIMEOUT,
            "token_endpoint": TOKEN_ENDPOINT,
            "token_timeout": 8,
            "scope": DEFAULT_SCOPE,
        },
    }


@app.post("/api/accounts")
async def inspect_accounts(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate account text."""
    account_text = payload.get("account_text", "")
    if not account_text:
        raise ValueError("account_text is required")
    
    accounts = parse_accounts(account_text.splitlines())
    return {
        "account_file": None,
        "count": len(accounts),
        "accounts": [
            {
                "line": account.source_line,
                "email": account.email,
                "password": account.masked_password,
                "client_id": account.client_id,
                "refresh_token": account.masked_refresh_token,
            }
            for account in accounts
        ],
    }


@app.post("/api/fetch")
async def fetch_mail(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch mail for accounts (HTTP endpoint, no WebSocket)."""
    # For backward compatibility, keep the original fetch logic
    # In production, use WebSocket for real-time progress
    from .web import fetch_data
    config = WebConfig()
    return fetch_data(payload, config)


@app.websocket("/ws/fetch")
async def websocket_fetch(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time mail fetching with progress updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Receive fetch request
            data = await websocket.receive_json()
            
            account_text = data.get("account_text", "")
            if not account_text:
                await manager.send_progress(websocket, {
                    "status": "error",
                    "message": "account_text is required",
                })
                continue
            
            # Parse accounts
            try:
                accounts = parse_accounts(account_text.splitlines())
            except AccountFormatError as exc:
                await manager.send_progress(websocket, {
                    "status": "error",
                    "message": str(exc),
                })
                continue
            
            # Fetch options
            mailbox = data.get("mailbox", "INBOX")
            limit = payload_int(data, "limit", 20)
            selected_account = data.get("account", "").strip()
            include_raw = data.get("include_raw", False)
            
            if selected_account:
                accounts = filter_accounts_by_email(accounts, selected_account)
            
            options = AccountFetchOptions(
                mailbox=mailbox,
                limit=limit,
                max_bytes=None if include_raw else 16 * 1024,
                host=data.get("imap_host", DEFAULT_IMAP_HOST),
                port=payload_int(data, "imap_port", DEFAULT_IMAP_PORT),
                imap_timeout=payload_int(data, "imap_timeout", DEFAULT_IMAP_TIMEOUT),
                token_endpoint=data.get("token_endpoint", TOKEN_ENDPOINT),
                scope=data.get("scope", DEFAULT_SCOPE),
                token_timeout=payload_int(data, "token_timeout", 8),
                debug=False,
            )
            
            fetcher = OutlookAccountMailFetcher(fetch_function=fetch_messages)
            
            # Send initial progress
            await manager.send_progress(websocket, {
                "status": "started",
                "total": len(accounts),
                "completed": 0,
                "failed": 0,
            })
            
            # Fetch with progress tracking
            completed = 0
            failed = 0
            all_messages = []
            
            for account in accounts:
                try:
                    # Fetch single account
                    result = fetcher.fetch(account, options, FetchDiagnostics())
                    completed += 1
                    all_messages.extend(result)
                    
                    await manager.send_progress(websocket, {
                        "status": "progress",
                        "account": account.email,
                        "completed": completed,
                        "failed": failed,
                        "total": len(accounts),
                        "messages": len(result),
                    })
                except Exception as exc:
                    failed += 1
                    LOGGER.error("Fetch failed for %s: %s", account.email, exc)
                    await manager.send_progress(websocket, {
                        "status": "account_failed",
                        "account": account.email,
                        "error": str(exc),
                        "completed": completed,
                        "failed": failed,
                        "total": len(accounts),
                    })
            
            # Send completion
            await manager.send_progress(websocket, {
                "status": "completed",
                "total": len(accounts),
                "completed": completed,
                "failed": failed,
                "messages": len(all_messages),
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        LOGGER.error("WebSocket error: %s", exc)
        await manager.send_progress(websocket, {
            "status": "error",
            "message": str(exc),
        })
        manager.disconnect(websocket)


@app.get("/")
async def root() -> HTMLResponse:
    """Serve the frontend application."""
    with open("frontend/dist/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
