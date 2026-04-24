"""
Ingestion module. Public API: fetch_new_posts()

Fetches tweets from Apify (default) or X API v2, upserts accounts + posts into DB,
and returns newly-inserted Post objects. Logs every run to ingestion_runs.

DATA_PROVIDER env var controls which source is used: "apify" or "xapi".
"""
import asyncio
import logging
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Account, IngestionRun, Post

log = logging.getLogger(__name__)

_APIFY_BASE = "https://api.apify.com/v2"
_APIFY_ACTOR = "quacker/twitter-scraper"  # configure in .env if needed
_XAPI_BASE = "https://api.twitter.com/2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engagement(likes: int, retweets: int, replies: int) -> float:
    raw = likes + 3 * retweets + replies + 1
    return min(1.0, math.log(raw) / math.log(10_000))


def _parse_dt(raw: str) -> datetime:
    if not raw:
        return datetime.utcnow()
    try:
        return parsedate_to_datetime(raw).replace(tzinfo=None)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.rstrip("Z"))
    except Exception:
        return datetime.utcnow()


def _parse_apify_item(item: dict) -> Optional[dict]:
    """Normalize one Apify tweet item into our internal dict. Returns None if unusable."""
    tweet_id = str(
        item.get("id") or item.get("id_str") or item.get("tweetId") or ""
    ).strip()
    if not tweet_id:
        return None

    text = (item.get("full_text") or item.get("text") or item.get("fullText") or "").strip()
    if not text:
        return None

    user = item.get("user") or item.get("author") or {}
    username = (
        (
            user.get("screen_name")
            or user.get("username")
            or item.get("screen_name")
            or item.get("username")
            or ""
        )
        .lstrip("@")
        .strip()
    )
    if not username:
        return None

    x_author_id = str(user.get("id_str") or user.get("id") or user.get("userId") or username)
    display_name = user.get("name") or user.get("displayName") or username
    follower_count = int(user.get("followers_count") or user.get("followersCount") or 0)
    likes = int(item.get("favorite_count") or item.get("likeCount") or item.get("likes") or 0)
    retweets = int(item.get("retweet_count") or item.get("retweetCount") or item.get("retweets") or 0)
    replies = int(item.get("reply_count") or item.get("replyCount") or item.get("replies") or 0)
    canonical = (
        item.get("url")
        or item.get("twitter_url")
        or item.get("twitterUrl")
        or f"https://x.com/{username}/status/{tweet_id}"
    )
    return {
        "tweet_id": tweet_id,
        "text": text,
        "username": username,
        "x_author_id": x_author_id,
        "display_name": display_name,
        "follower_count": follower_count,
        "canonical_x_url": canonical,
        "posted_at": _parse_dt(item.get("created_at") or item.get("createdAt") or ""),
        "likes_count": likes,
        "retweets_count": retweets,
        "replies_count": replies,
        "engagement_score": _engagement(likes, retweets, replies),
    }


# ---------------------------------------------------------------------------
# Data provider: Apify
# ---------------------------------------------------------------------------

async def _apify_fetch(handles: list[str]) -> list[dict]:
    """Start an Apify run, poll until done, return normalized post dicts."""
    if not settings.apify_api_token:
        log.warning("APIFY_API_TOKEN not set — skipping Apify ingestion")
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        # Start run
        resp = await client.post(
            f"{_APIFY_BASE}/acts/{_APIFY_ACTOR}/runs",
            params={"token": settings.apify_api_token},
            json={
                "startUrls": [{"url": f"https://twitter.com/{h}"} for h in handles],
                "maxItems": 200,
            },
        )
        resp.raise_for_status()
        run_id = resp.json()["data"]["id"]
        log.info("Apify run %s started for %d handles", run_id, len(handles))

        # Poll for completion (up to 5 min)
        dataset_id: Optional[str] = None
        for _ in range(60):
            await asyncio.sleep(5)
            poll = await client.get(
                f"{_APIFY_BASE}/actor-runs/{run_id}",
                params={"token": settings.apify_api_token},
            )
            run_data = poll.json()["data"]
            status = run_data["status"]
            if status == "SUCCEEDED":
                dataset_id = run_data["defaultDatasetId"]
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Apify run ended with status {status}")

        if dataset_id is None:
            raise TimeoutError("Apify run did not complete within 5 minutes")

        # Fetch dataset items
        items_resp = await client.get(
            f"{_APIFY_BASE}/datasets/{dataset_id}/items",
            params={"token": settings.apify_api_token, "limit": 500},
        )
        items_resp.raise_for_status()
        raw = items_resp.json()

    normalized = [_parse_apify_item(i) for i in raw]
    return [n for n in normalized if n is not None]


# ---------------------------------------------------------------------------
# Data provider: X API v2
# ---------------------------------------------------------------------------

async def _xapi_fetch(handles: list[str]) -> list[dict]:
    """Fetch recent tweets via X API v2 search. Returns normalized post dicts."""
    if not settings.x_api_bearer_token:
        log.warning("X_API_BEARER_TOKEN not set — skipping X API ingestion")
        return []

    headers = {"Authorization": f"Bearer {settings.x_api_bearer_token}"}
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        for handle in handles:
            resp = await client.get(
                f"{_XAPI_BASE}/tweets/search/recent",
                params={
                    "query": f"from:{handle} -is:retweet",
                    "max_results": 10,
                    "tweet.fields": "created_at,public_metrics,author_id",
                    "expansions": "author_id",
                    "user.fields": "username,name,public_metrics",
                },
            )
            if resp.status_code != 200:
                log.warning("X API error for @%s: HTTP %s", handle, resp.status_code)
                continue

            body = resp.json()
            users = {u["id"]: u for u in body.get("includes", {}).get("users", [])}

            for tweet in body.get("data", []):
                author = users.get(tweet.get("author_id"), {})
                m = tweet.get("public_metrics", {})
                uname = author.get("username", handle)
                tid = tweet["id"]
                likes = m.get("like_count", 0)
                rts = m.get("retweet_count", 0)
                reps = m.get("reply_count", 0)
                results.append(
                    {
                        "tweet_id": tid,
                        "text": tweet["text"],
                        "username": uname,
                        "x_author_id": tweet.get("author_id", uname),
                        "display_name": author.get("name", uname),
                        "follower_count": author.get("public_metrics", {}).get(
                            "followers_count", 0
                        ),
                        "canonical_x_url": f"https://x.com/{uname}/status/{tid}",
                        "posted_at": _parse_dt(tweet.get("created_at", "")),
                        "likes_count": likes,
                        "retweets_count": rts,
                        "replies_count": reps,
                        "engagement_score": _engagement(likes, rts, reps),
                    }
                )

    return results


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _upsert_account(db: AsyncSession, item: dict) -> int:
    result = await db.execute(select(Account).where(Account.x_id == item["x_author_id"]))
    account = result.scalar_one_or_none()
    if account is None:
        account = Account(
            x_id=item["x_author_id"],
            username=item["username"],
            display_name=item["display_name"],
            follower_count=item["follower_count"],
        )
        db.add(account)
        await db.flush()
    else:
        account.follower_count = item["follower_count"]
        account.last_checked_at = datetime.utcnow()
    return account.id


async def _upsert_posts(db: AsyncSession, normalized: list[dict]) -> list[Post]:
    """Insert posts not already in DB. Returns new Post objects."""
    if not normalized:
        return []

    tweet_ids = [n["tweet_id"] for n in normalized]
    existing_ids = set(
        (await db.execute(select(Post.x_id).where(Post.x_id.in_(tweet_ids)))).scalars().all()
    )

    new_posts: list[Post] = []
    for item in normalized:
        if item["tweet_id"] in existing_ids:
            continue
        account_id = await _upsert_account(db, item)
        post = Post(
            x_id=item["tweet_id"],
            canonical_x_url=item["canonical_x_url"],
            account_id=account_id,
            text_content=item["text"],
            engagement_score=item["engagement_score"],
            likes_count=item["likes_count"],
            retweets_count=item["retweets_count"],
            replies_count=item["replies_count"],
            posted_at=item["posted_at"],
        )
        db.add(post)
        new_posts.append(post)

    if new_posts:
        await db.flush()

    return new_posts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_new_posts() -> list[Post]:
    """
    Fetch recent posts from all active accounts, upsert into DB, return new Posts.

    Controls which provider is used via DATA_PROVIDER env var ("apify" or "xapi").
    Every call records an IngestionRun for audit/monitoring.
    """
    async with get_session() as db:
        run = IngestionRun(
            source=settings.data_provider,
            started_at=datetime.now(timezone.utc),
            status="in_progress",
        )
        db.add(run)
        await db.flush()

        try:
            handles_result = await db.execute(
                select(Account.username).where(Account.is_active == True)  # noqa: E712
            )
            handles = list(handles_result.scalars().all())

            if not handles:
                log.info("No active accounts in DB — ingestion no-op")
                normalized: list[dict] = []
            elif settings.data_provider == "apify":
                normalized = await _apify_fetch(handles)
            else:
                normalized = await _xapi_fetch(handles)

            new_posts = await _upsert_posts(db, normalized)

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.posts_ingested = len(normalized)
            run.posts_new = len(new_posts)
            await db.commit()

            log.info(
                "Ingestion done: provider=%s fetched=%d new=%d",
                settings.data_provider,
                len(normalized),
                len(new_posts),
            )
            return new_posts

        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)[:500]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            log.error("Ingestion failed: %s", exc)
            raise
