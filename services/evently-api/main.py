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

class CreateEventRequest(BaseModel):
    type: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(..., min_length=1)
    idempotency_key: Optional[str] = None

class CreateEventResponse(BaseModel):
    event_id: str
    job_ids: List[str]
    
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


@app.post("/events", status_code=201, response_model=CreateEventResponse)
async def create_event(req: CreateEventRequest):
    pool = app.state.db_pool

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1) Insert event (idempotent if idempotency_key provided)
            if req.idempotency_key:
                event_id = await conn.fetchval(
                    """
                    INSERT INTO events (type, payload, idempotency_key)
                    VALUES ($1, $2::jsonb, $3)
                    ON CONFLICT (type, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                    DO UPDATE SET payload = EXCLUDED.payload
                    RETURNING id::text
                    """,
                    req.type,
                    json.dumps(req.payload),
                    req.idempotency_key,
                )
            else:
                event_id = await conn.fetchval(
                    """
                    INSERT INTO events (type, payload)
                    VALUES ($1, $2::jsonb)
                    RETURNING id::text
                    """,
                    req.type,
                    json.dumps(req.payload),
                )

            # 2) Find enabled routes for this event type
            routes = await conn.fetch(
                """
                SELECT id::text AS id, action_type, destination, retry_policy
                FROM routes
                WHERE event_type = $1 AND enabled = TRUE
                """,
                req.type,
            )

            job_ids: List[str] = []

            # 3) Create one job per route
            for r in routes:
                route_id = r["id"]
                action_type = r["action_type"]

                # Parse retry_policy.max_attempts (robust: dict or string)
                retry_policy = r["retry_policy"]
                if isinstance(retry_policy, str):
                    try:
                        retry_policy = json.loads(retry_policy)
                    except json.JSONDecodeError:
                        retry_policy = {}

                max_attempts = 5
                if isinstance(retry_policy, dict):
                    v = retry_policy.get("max_attempts")
                    if isinstance(v, int) and v > 0:
                        max_attempts = v

                # Insert job. For MVP: job.payload = event.payload
                job_id = await conn.fetchval(
                    """
                    INSERT INTO jobs (event_id, route_id, action_type, payload, status, attempt, max_attempts)
                    VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, 'queued', 0, $5)
                    RETURNING id::text
                    """,
                    event_id,
                    route_id,
                    action_type,
                    json.dumps(req.payload),
                    max_attempts,
                )

                job_ids.append(job_id)

            return CreateEventResponse(event_id=event_id, job_ids=job_ids)