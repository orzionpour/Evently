import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional, List

import asyncpg
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")


# ---------- Models ----------

class Destination(BaseModel):
    url: str = Field(..., min_length=1)
    timeout_ms: Optional[int] = Field(default=3000, ge=1)
    headers: Optional[Dict[str, str]] = None
    secret: Optional[str] = None  # for later (HMAC signing)


class RetryPolicy(BaseModel):
    max_attempts: int = Field(..., ge=1)
    backoff: Optional[str] = None  # for later (e.g. "1m,5m,30m")


class CreateRouteRequest(BaseModel):
    event_type: str = Field(..., min_length=1)
    action_type: str = Field(..., min_length=1)
    destination: Destination
    retry_policy: RetryPolicy
    enabled: Optional[bool] = True


class CreateRouteResponse(BaseModel):
    id: str


class RouteResponse(BaseModel):
    id: str
    event_type: str
    action_type: str
    destination: Dict[str, Any]
    retry_policy: Dict[str, Any]
    enabled: bool
    created_at: datetime


# ---------- Lifespan / DB Pool ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
    )
    yield
    await app.state.db_pool.close()


app = FastAPI(lifespan=lifespan)


# ---------- Health ----------

@app.get("/health")
async def health():
    return {"ok": True}


# ---------- Routes Endpoints ----------

@app.post("/routes", status_code=201, response_model=CreateRouteResponse)
async def create_route(req: CreateRouteRequest):
    # MVP guardrail: only allow webhook.deliver for now
    if req.action_type != "webhook.deliver":
        raise HTTPException(status_code=400, detail="action_type must be 'webhook.deliver' (MVP)")

    pool = app.state.db_pool
    async with pool.acquire() as conn:
        route_id = await conn.fetchval(
            """
            INSERT INTO routes (event_type, action_type, destination, retry_policy, enabled)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, $5)
            RETURNING id::text
            """,
            req.event_type,
            req.action_type,
            json.dumps(req.destination.model_dump()),
            json.dumps(req.retry_policy.model_dump()),
            bool(req.enabled),
        )


    return CreateRouteResponse(id=route_id)


@app.get("/routes", response_model=List[RouteResponse])
async def list_routes():
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              id::text AS id,
              event_type,
              action_type,
              destination,
              retry_policy,
              enabled,
              created_at
            FROM routes
            ORDER BY created_at DESC
            LIMIT 100
            """
        )

    out: List[RouteResponse] = []
    for r in rows:
        dest = r["destination"]
        rp = r["retry_policy"]

        # Be robust across driver/codec differences:
        # - sometimes jsonb is already a dict
        # - sometimes it can come back as a JSON string
        if isinstance(dest, str):
            dest = json.loads(dest)
        if isinstance(rp, str):
            rp = json.loads(rp)

        out.append(
            RouteResponse(
                id=r["id"],
                event_type=r["event_type"],
                action_type=r["action_type"],
                destination=dest,
                retry_policy=rp,
                enabled=r["enabled"],
                created_at=r["created_at"],
            )
        )

    return out


