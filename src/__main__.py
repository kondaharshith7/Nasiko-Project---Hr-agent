"""
HR Nexus — FastAPI A2A Server
Single entry point for the unified HR agent.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uuid
import json
import logging
import click
import uvicorn
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from agent import HRNexusAgent
from models import JsonRpcRequest, JsonRpcResponse, Task, TaskStatus, Artifact, ArtifactPart

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s"
)
logger = logging.getLogger("hr-nexus")

app = FastAPI(
    title="HR Nexus",
    description="Unified HR Agent — Leave, Data, JD Generation, and Recruitment",
    version="1.0.0"
)

# Per-session agent instances for conversation continuity
_sessions: Dict[str, HRNexusAgent] = {}


def get_agent(session_id: str) -> HRNexusAgent:
    if session_id not in _sessions:
        logger.info(f"🆕 New session: {session_id[:8]}")
        _sessions[session_id] = HRNexusAgent()
    return _sessions[session_id]


@app.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card():
    card_path = Path(__file__).parent.parent / "AgentCard.json"
    if not card_path.exists():
        return JSONResponse({"error": "AgentCard.json not found"}, status_code=404)
    with open(card_path, "r") as f:
        return JSONResponse(content=json.load(f))


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "HR Nexus", "version": "1.0.0"}


@app.post("/")
async def handle_rpc(request: JsonRpcRequest):
    if request.method != "message/send":
        raise HTTPException(status_code=404, detail=f"Unknown method: {request.method}")

    try:
        session_id = request.params.session_id or str(uuid.uuid4())
        input_text = " ".join(
            p.text for p in request.params.message.parts
            if p.kind == "text" and p.text
        )

        logger.info(f"[{session_id[:8]}] → {input_text[:120]}")

        agent    = get_agent(session_id)
        response = agent.process(input_text)

        logger.info(f"[{session_id[:8]}] ← {response[:120]}")

        return JsonRpcResponse(
            id=request.id,
            result=Task(
                id=str(uuid.uuid4()),
                status=TaskStatus(state="completed", timestamp=datetime.now().isoformat()),
                artifacts=[Artifact(parts=[ArtifactPart(text=response)])],
                contextId=session_id
            )
        )

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@click.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=5000, show_default=True)
def main(host: str, port: int):
    logger.info("🚀 HR Nexus starting up…")
    logger.info(f"📡 Listening on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
