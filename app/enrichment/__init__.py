"""
Enrichment module. Public API: enrich_protocol(protocol_id)

Gathers context for a DeFi protocol and caches it in CoverageProfile.
Cache TTL defaults to 6 hours (COVERAGE_CACHE_TTL_SECONDS env var).

Current enrichment data (Phase 3 — no external API calls required):
  - recent_post_count: posts mentioning the protocol in last 48 h
  - latest_post_url:   canonical URL of the most recent mention
  - coverage_gap:      True if no posts in the last 24 h

Returns the updated CoverageProfile object.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_session
from app.models import CoverageProfile, Post, Protocol

log = logging.getLogger(__name__)


def _is_stale(profile: CoverageProfile) -> bool:
    if profile.last_enriched_at is None:
        return True
    ttl = profile.cache_ttl_seconds or settings.coverage_cache_ttl_seconds
    last = profile.last_enriched_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() > ttl


async def _gather_enrichment(db, protocol: Protocol) -> dict:
    """Count recent mentions and find latest post URL for the protocol."""
    cutoff_48h = datetime.utcnow() - timedelta(hours=48)
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)

    # Posts mentioning the protocol by name or symbol in last 48 h
    name_pattern = f"%{protocol.name}%"
    symbol_pattern = f"%{protocol.symbol}%" if protocol.symbol else None

    base_filter = Post.posted_at >= cutoff_48h
    name_cond = Post.text_content.ilike(name_pattern)
    cond = name_cond if symbol_pattern is None else (name_cond | Post.text_content.ilike(symbol_pattern))

    count_result = await db.execute(
        select(func.count(Post.id)).where(base_filter, cond)
    )
    recent_post_count = count_result.scalar() or 0

    # Latest post URL
    latest_result = await db.execute(
        select(Post.canonical_x_url, Post.posted_at)
        .where(base_filter, cond)
        .order_by(Post.posted_at.desc())
        .limit(1)
    )
    latest_row = latest_result.first()
    latest_post_url = latest_row[0] if latest_row else None

    # Coverage gap: no posts in last 24 h
    gap_result = await db.execute(
        select(func.count(Post.id)).where(Post.posted_at >= cutoff_24h, cond)
    )
    coverage_gap = (gap_result.scalar() or 0) == 0

    return {
        "recent_post_count": recent_post_count,
        "latest_post_url": latest_post_url,
        "coverage_gap": coverage_gap,
        "enriched_at": datetime.utcnow().isoformat(),
    }


async def enrich_protocol(protocol_id: int) -> CoverageProfile:
    """
    Ensure the CoverageProfile for a protocol is populated and fresh.

    Returns cached data if within TTL; otherwise re-runs enrichment and
    updates the profile. Raises ValueError if the protocol doesn't exist.
    """
    async with get_session() as db:
        result = await db.execute(
            select(Protocol)
            .where(Protocol.id == protocol_id)
            .options(selectinload(Protocol.coverage_profiles))
        )
        protocol = result.scalar_one_or_none()

        if protocol is None:
            raise ValueError(f"Protocol {protocol_id} not found")

        # Get or create profile
        profile = protocol.coverage_profiles[0] if protocol.coverage_profiles else None

        if profile is None:
            profile = CoverageProfile(
                protocol_id=protocol_id,
                cache_ttl_seconds=settings.coverage_cache_ttl_seconds,
            )
            db.add(profile)
            await db.flush()

        if not _is_stale(profile):
            log.debug("Protocol %d enrichment cache is fresh — skipping", protocol_id)
            return profile

        log.info("Enriching protocol %d (%s)", protocol_id, protocol.name)
        data = await _gather_enrichment(db, protocol)

        profile.enrichment_config = json.dumps(data)
        profile.last_enriched_at = datetime.utcnow()
        await db.commit()

        log.info(
            "Protocol %d enriched: %d recent posts, gap=%s",
            protocol_id,
            data["recent_post_count"],
            data["coverage_gap"],
        )
        return profile
