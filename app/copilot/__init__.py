"""
Copilot module. Public API: generate_brief(cluster_id)

Generates an analyst-grade research brief for a SignalCluster using
Claude Sonnet 4.6. Non-negotiable constraints:
  - Every claim must cite a source X post URL.
  - Ungrounded or inferred claims are labeled [HYPOTHESIS].
  - canonical_x_url is verified non-null for every post before the call.

Returns the brief as a plain string.
"""
import logging
from datetime import datetime

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import get_session
from app.models import Post, SignalCluster

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior DeFi research analyst. Your job is to produce a concise, \
grounded research brief from a cluster of X (Twitter) posts. \

Rules you must follow without exception:
1. Every factual claim must be followed by a citation: (source: <X_URL>)
2. Any inference or interpretation not directly stated in a source post \
   must be labeled [HYPOTHESIS].
3. Do not fabricate metrics, TVL figures, or protocol names that are not \
   present in the provided posts.
4. Structure: one paragraph summary, then bullet-point key signals, \
   then a one-sentence analyst verdict.
5. Keep the brief under 400 words.
"""

_USER_TEMPLATE = """\
Cluster topic: {topic}
Alpha score: {alpha_score:.3f}
Post count: {post_count}
Date range: {date_range}

--- SOURCE POSTS ---
{posts_block}
---

Write the research brief now.
"""


def _format_posts_block(posts: list[Post]) -> str:
    lines = []
    for i, post in enumerate(posts, 1):
        ts = post.posted_at.strftime("%Y-%m-%d %H:%M UTC") if post.posted_at else "unknown"
        lines.append(
            f"[{i}] {ts} | {post.canonical_x_url}\n"
            f"    {post.text_content[:500]}"
        )
    return "\n\n".join(lines)


async def generate_brief(cluster_id: int) -> str:
    """
    Generate a cited analyst brief for the given SignalCluster.

    Raises:
        ValueError: if the cluster doesn't exist or has no posts.
        RuntimeError: if any post is missing canonical_x_url (non-negotiable).
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
            raise ValueError(f"Cluster {cluster_id} has no posts — cannot generate brief")

        # Non-negotiable: every post must have canonical_x_url
        missing = [p.id for p in posts if not p.canonical_x_url]
        if missing:
            raise RuntimeError(
                f"Posts {missing} are missing canonical_x_url — broken state, refusing to generate brief"
            )

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

        posts_sorted = sorted(posts, key=lambda p: p.posted_at or datetime.min, reverse=True)

        dates = [p.posted_at for p in posts if p.posted_at]
        if dates:
            date_range = f"{min(dates).strftime('%Y-%m-%d')} – {max(dates).strftime('%Y-%m-%d')}"
        else:
            date_range = "unknown"

        user_content = _USER_TEMPLATE.format(
            topic=cluster.topic or cluster.name,
            alpha_score=cluster.research_alpha_score or 0.0,
            post_count=len(posts),
            date_range=date_range,
            posts_block=_format_posts_block(posts_sorted),
        )

    # Call Claude outside the DB session — no need to hold the connection open
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.copilot_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    brief = message.content[0].text
    log.info(
        "Brief generated for cluster %d (%d posts, %d tokens used)",
        cluster_id,
        len(posts),
        message.usage.output_tokens,
    )
    return brief
