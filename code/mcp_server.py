"""MCP stdio server — exposes the triage pipeline as an MCP tool.

Follows MCP Protocol 2024-11-05 (JSON-RPC 2.0 over stdio).
Claude Code, Cursor, and any MCP-aware client can connect via:

    python code/mcp_server.py

Exposed tool:
    triage_ticket(ticket, company, subject) -> TicketOutput dict

Transport: newline-delimited JSON on stdin/stdout.
All logging goes to stderr so it never contaminates the JSON stream.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow running as `python code/mcp_server.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain.types import TicketState
from pipeline import PipelineFactory

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[mcp_server] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── MCP tool schema ────────────────────────────────────────────────────────────

_TOOL_SCHEMA = {
    "name": "triage_ticket",
    "description": (
        "Run a support ticket through the multi-agent triage pipeline. "
        "Returns status, product_area, response, justification, and request_type."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticket": {
                "type": "string",
                "description": "The full text of the support ticket.",
            },
            "company": {
                "type": "string",
                "description": "Company name (HackerRank | Claude | Visa).",
                "default": "",
            },
            "subject": {
                "type": "string",
                "description": "Short subject line for the ticket.",
                "default": "",
            },
        },
        "required": ["ticket"],
    },
}

SERVER_INFO = {
    "name": "hackerrank-triage-agent",
    "version": "1.0.0",
}

PROTOCOL_VERSION = "2024-11-05"


# ── Pipeline singleton ─────────────────────────────────────────────────────────

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        log.info("Initializing pipeline (first call)…")
        _pipeline = PipelineFactory.create()
        log.info("Pipeline ready.")
    return _pipeline


# ── JSON-RPC helpers ───────────────────────────────────────────────────────────

def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str, data: Any = None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _send(obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ── Request handlers ───────────────────────────────────────────────────────────

def handle_initialize(req_id: Any, params: dict) -> dict:
    return _ok(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": SERVER_INFO,
    })


def handle_tools_list(req_id: Any, params: dict) -> dict:
    return _ok(req_id, {"tools": [_TOOL_SCHEMA]})


def handle_tools_call(req_id: Any, params: dict) -> dict:
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name != "triage_ticket":
        return _err(req_id, -32601, f"Unknown tool: {tool_name!r}")

    ticket = (arguments.get("ticket") or "").strip()
    company = (arguments.get("company") or "").strip()
    subject = (arguments.get("subject") or "").strip()

    if not ticket:
        return _err(req_id, -32602, "Missing required argument: 'ticket'")

    try:
        pipeline = _get_pipeline()
        state = TicketState(ticket=ticket, subject=subject, company=company)
        output = pipeline.run(state)
        result_dict = output.to_dict()

        return _ok(req_id, {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result_dict, indent=2, ensure_ascii=False),
                }
            ],
        })
    except Exception as exc:
        log.exception("Pipeline error")
        return _err(req_id, -32603, f"Pipeline error: {exc}")


def handle_ping(req_id: Any, params: dict) -> dict:
    return _ok(req_id, {})


_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "ping": handle_ping,
}


# ── Main loop ──────────────────────────────────────────────────────────────────

def serve() -> None:
    log.info("MCP server started — listening on stdin.")

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            req = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _send(_err(None, -32700, f"Parse error: {exc}"))
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        log.info("→ %s (id=%s)", method, req_id)

        handler = _HANDLERS.get(method)
        if handler is None:
            # Notifications (no id) are silently ignored per JSON-RPC spec
            if req_id is not None:
                _send(_err(req_id, -32601, f"Method not found: {method!r}"))
            continue

        try:
            response = handler(req_id, params)
            _send(response)
        except Exception as exc:
            log.exception("Unhandled error in handler %s", method)
            _send(_err(req_id, -32603, f"Internal error: {exc}"))

    log.info("stdin closed — shutting down.")


if __name__ == "__main__":
    serve()
