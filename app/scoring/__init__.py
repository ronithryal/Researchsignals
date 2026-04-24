"""
Scoring module. Public API: score_cluster(cluster_id)

Computes a research_alpha_score in [0, 1] for a SignalCluster:

  score = 0.50 × engagement  (avg normalized engagement across posts)
        + 0.30 × temporal    (recency decay — newer clusters score higher)
        + 0.20 × semantic    (DeFi keyword density)

Updates cluster.research_alpha_score in DB and returns the score.
"""
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Post, SignalCluster

log = logging.getLogger(__name__)

_DEFI_KEYWORDS = frozenset(
    {
        "defi", "yield", "liquidity", "tvl", "protocol", "dao", "governance",
        "vault", "staking", "lending", "borrowing", "amm", "dex", "swap",
        "tokenomics", "alpha", "apy", "apr", "collateral", "leverage",
        "liquidation", "impermanent", "pool", "lp", "farm", "incentive",
        "aave", "uniswap", "curve", "compound", "maker", "synthetix",
        "balancer", "yearn", "convex", "frax", "lido", "eigenlayer",
    }
)

_TEMPORAL_HALF_LIFE_DAYS = 7.0  # score halves every 7 days


def _engagement_component(posts: list[Post]) -> float:
    if not posts:
        return 0.0
    scores = [p.engagement_score or 0.0 for p in posts]
    return sum(scores) / len(scores)


def _temporal_component(posts: list[Post]) -> float:
    if not posts:
        return 0.0
    now = datetime.now(timezone.utc)
    newest = max(
        (p.posted_at for p in posts if p.posted_at),
        default=datetime.utcnow(),
    )
    # Ensure tz-aware comparison
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age_days = (now - newest).total_seconds() / 86_400
    return math.exp(-age_days * math.log(2) / _TEMPORAL_HALF_LIFE_DAYS)


def _semantic_component(posts: list[Post]) -> float:
    if not posts:
        return 0.0
    total_words = 0
    keyword_hits = 0
    for post in posts:
        words = post.text_content.lower().split()
        total_words += len(words)
        keyword_hits += sum(1 for w in words if w.strip(".,!?#@") in _DEFI_KEYWORDS)
    if total_words == 0:
        return 0.0
    density = keyword_hits / total_words
    # Scale so ~5 % keyword density → score ≈ 1.0; cap at 1.0
    return min(1.0, density * 20)


async def score_cluster(cluster_id: int) -> float:
    """
    Compute and persist research_alpha_score for the given cluster.

    Returns the updated score in [0, 1]. Raises ValueError if the cluster
    does not exist.
    """
    async with get_session() as db:
        result = await db.execute(
            select(SignalCluster)
            .where(SignalCluster.id == cluster_id)
            .options(selectinload(SignalCluster.posts))
        )
        cluster = result.scalar_one_or_none()

        if cluster is None:
            raise ValueError(f"SignalCluster {cluster_id} not found")

        posts = cluster.posts

        if not posts:
            log.warning("Cluster %d has no posts — score stays 0", cluster_id)
            return 0.0

        engagement = _engagement_component(posts)
        temporal = _temporal_component(posts)
        semantic = _semantic_component(posts)

        score = round(0.50 * engagement + 0.30 * temporal + 0.20 * semantic, 6)
        score = max(0.0, min(1.0, score))

        cluster.research_alpha_score = score
        await db.commit()

        log.info(
            "Cluster %d scored %.4f (eng=%.3f temporal=%.3f semantic=%.3f)",
            cluster_id, score, engagement, temporal, semantic,
        )
        return score
