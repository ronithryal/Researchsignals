import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.copilot import generate_brief
from app.db import get_session
from app.models import AlertRule, IngestionRun, Post, Protocol, SignalCluster

router = APIRouter(prefix="/api", tags=["phase4"])


def _post_payload(post: Post) -> dict:
    return {
        "id": post.id,
        "xId": post.x_id,
        "canonicalXUrl": post.canonical_x_url,
        "accountId": post.account_id,
        "username": post.account.username if post.account else None,
        "textContent": post.text_content,
        "engagementScore": post.engagement_score,
        "likesCount": post.likes_count,
        "retweetsCount": post.retweets_count,
        "repliesCount": post.replies_count,
        "postedAt": post.posted_at,
        "ingestedAt": post.ingested_at,
    }


def _cluster_payload(cluster: SignalCluster) -> dict:
    post_items = [_post_payload(p) for p in cluster.posts]
    return {
        "id": cluster.id,
        "name": cluster.name,
        "description": cluster.description,
        "topic": cluster.topic,
        "primaryXUrl": cluster.primary_x_url,
        "researchAlphaScore": cluster.research_alpha_score,
        "confidenceScore": cluster.confidence_score,
        "postCount": cluster.post_count,
        "isArchived": cluster.is_archived,
        "createdAt": cluster.created_at,
        "updatedAt": cluster.updated_at,
        "posts": post_items,
    }


@router.get("/posts")
async def get_posts(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    async with get_session() as db:
        total = (await db.execute(select(func.count(Post.id)))).scalar() or 0
        result = await db.execute(
            select(Post)
            .options(selectinload(Post.account))
            .order_by(Post.posted_at.desc())
            .offset(offset)
            .limit(limit)
        )
        posts = result.scalars().all()

    return {"total": total, "items": [_post_payload(post) for post in posts]}


@router.get("/clusters")
async def get_clusters(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    async with get_session() as db:
        total = (await db.execute(select(func.count(SignalCluster.id)))).scalar() or 0
        result = await db.execute(
            select(SignalCluster)
            .options(selectinload(SignalCluster.posts).selectinload(Post.account))
            .where(SignalCluster.is_archived == False)  # noqa: E712
            .order_by(SignalCluster.research_alpha_score.desc(), SignalCluster.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        clusters = result.scalars().all()

    return {"total": total, "items": [_cluster_payload(cluster) for cluster in clusters]}


@router.get("/clusters/{cluster_id}/brief")
async def get_cluster_brief(cluster_id: int):
    try:
        brief = await generate_brief(cluster_id)
        return {"clusterId": cluster_id, "brief": brief}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/protocols/{protocol_id}")
async def get_protocol(protocol_id: int):
    async with get_session() as db:
        result = await db.execute(
            select(Protocol)
            .where(Protocol.id == protocol_id)
            .options(selectinload(Protocol.coverage_profiles), selectinload(Protocol.alert_rules))
        )
        protocol = result.scalar_one_or_none()

        if protocol is None:
            raise HTTPException(status_code=404, detail=f"Protocol {protocol_id} not found")

        coverage_profile = protocol.coverage_profiles[0] if protocol.coverage_profiles else None
        enrichment = None
        if coverage_profile and coverage_profile.enrichment_config:
            try:
                enrichment = json.loads(coverage_profile.enrichment_config)
            except json.JSONDecodeError:
                enrichment = {"raw": coverage_profile.enrichment_config}

        return {
            "id": protocol.id,
            "name": protocol.name,
            "symbol": protocol.symbol,
            "description": protocol.description,
            "website": protocol.website,
            "isActive": protocol.is_active,
            "coverageProfile": (
                {
                    "id": coverage_profile.id,
                    "isEnabled": coverage_profile.is_enabled,
                    "cacheTtlSeconds": coverage_profile.cache_ttl_seconds,
                    "lastEnrichedAt": coverage_profile.last_enriched_at,
                    "enrichment": enrichment,
                }
                if coverage_profile
                else None
            ),
            "alerts": [
                {
                    "id": alert.id,
                    "name": alert.name,
                    "description": alert.description,
                    "alphaScoreThreshold": alert.alpha_score_threshold,
                    "confidenceThreshold": alert.confidence_threshold,
                    "postCountThreshold": alert.post_count_threshold,
                    "isActive": alert.is_active,
                    "notificationChannel": alert.notification_channel,
                }
                for alert in protocol.alert_rules
            ],
        }


@router.get("/alerts")
async def list_alerts(protocol_id: Optional[int] = None):
    async with get_session() as db:
        stmt = select(AlertRule).order_by(AlertRule.created_at.desc())
        if protocol_id is not None:
            stmt = stmt.where(AlertRule.protocol_id == protocol_id)
        result = await db.execute(stmt)
        alerts = result.scalars().all()

    return {
        "items": [
            {
                "id": alert.id,
                "protocolId": alert.protocol_id,
                "name": alert.name,
                "description": alert.description,
                "alphaScoreThreshold": alert.alpha_score_threshold,
                "confidenceThreshold": alert.confidence_threshold,
                "postCountThreshold": alert.post_count_threshold,
                "isActive": alert.is_active,
                "notificationChannel": alert.notification_channel,
                "createdAt": alert.created_at,
                "updatedAt": alert.updated_at,
            }
            for alert in alerts
        ]
    }


@router.post("/alerts")
async def create_alert(payload: dict):
    protocol_id = payload.get("protocolId")
    name = payload.get("name")

    if not protocol_id or not name:
        raise HTTPException(status_code=400, detail="protocolId and name are required")

    async with get_session() as db:
        protocol = (
            await db.execute(select(Protocol.id).where(Protocol.id == protocol_id))
        ).scalar_one_or_none()
        if protocol is None:
            raise HTTPException(status_code=404, detail=f"Protocol {protocol_id} not found")

        alert = AlertRule(
            protocol_id=protocol_id,
            name=name,
            description=payload.get("description"),
            alpha_score_threshold=payload.get("alphaScoreThreshold", 0.0),
            confidence_threshold=payload.get("confidenceThreshold", 0.0),
            post_count_threshold=payload.get("postCountThreshold", 1),
            is_active=payload.get("isActive", True),
            notification_channel=payload.get("notificationChannel"),
        )
        db.add(alert)
        await db.flush()
        await db.commit()

    return {
        "id": alert.id,
        "protocolId": alert.protocol_id,
        "name": alert.name,
        "description": alert.description,
        "alphaScoreThreshold": alert.alpha_score_threshold,
        "confidenceThreshold": alert.confidence_threshold,
        "postCountThreshold": alert.post_count_threshold,
        "isActive": alert.is_active,
        "notificationChannel": alert.notification_channel,
        "createdAt": alert.created_at,
        "updatedAt": alert.updated_at,
    }


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: int, payload: dict):
    async with get_session() as db:
        alert = (await db.execute(select(AlertRule).where(AlertRule.id == alert_id))).scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        if "name" in payload:
            alert.name = payload["name"]
        if "description" in payload:
            alert.description = payload["description"]
        if "alphaScoreThreshold" in payload:
            alert.alpha_score_threshold = payload["alphaScoreThreshold"]
        if "confidenceThreshold" in payload:
            alert.confidence_threshold = payload["confidenceThreshold"]
        if "postCountThreshold" in payload:
            alert.post_count_threshold = payload["postCountThreshold"]
        if "isActive" in payload:
            alert.is_active = payload["isActive"]
        if "notificationChannel" in payload:
            alert.notification_channel = payload["notificationChannel"]

        await db.commit()

    return {"status": "updated", "id": alert_id}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    async with get_session() as db:
        alert = (await db.execute(select(AlertRule).where(AlertRule.id == alert_id))).scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        await db.delete(alert)
        await db.commit()

    return {"status": "deleted", "id": alert_id}


@router.get("/ingestion/status")
async def ingestion_status(limit: int = Query(default=10, ge=1, le=50)):
    async with get_session() as db:
        result = await db.execute(
            select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)
        )
        runs = result.scalars().all()

    if not runs:
        return {
            "hasRun": False,
            "status": "never_run",
            "isStale": True,
            "staleThresholdMinutes": settings.stale_data_threshold_minutes,
            "recentRuns": [],
        }

    latest = runs[0]
    completed_at = latest.completed_at or latest.started_at
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.stale_data_threshold_minutes)
    completed_aware = completed_at.replace(tzinfo=timezone.utc) if completed_at.tzinfo is None else completed_at
    is_stale = completed_aware < stale_cutoff

    return {
        "hasRun": True,
        "status": latest.status,
        "isStale": is_stale,
        "staleThresholdMinutes": settings.stale_data_threshold_minutes,
        "recentRuns": [
            {
                "id": run.id,
                "source": run.source,
                "status": run.status,
                "startedAt": run.started_at,
                "completedAt": run.completed_at,
                "postsIngested": run.posts_ingested,
                "postsNew": run.posts_new,
                "postsUpdated": run.posts_updated,
                "errorMessage": run.error_message,
            }
            for run in runs
        ],
    }
