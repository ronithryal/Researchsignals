"""
Clustering module. Public API: run_clustering(posts)

Groups a list of Post objects into SignalClusters using TF-IDF vectorization
and KMeans. Saves clusters to DB and links posts via the post_clusters table.
Returns the created SignalCluster objects.
"""
import logging
import math

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from app.db import get_session
from app.models import Post, SignalCluster, post_clusters

log = logging.getLogger(__name__)

_MIN_POSTS_TO_CLUSTER = 2


def _choose_k(n: int) -> int:
    """Heuristic: K ≈ sqrt(n/2), clamped to [2, 15]."""
    return max(2, min(int(math.ceil(math.sqrt(n / 2))), 15))


def _top_terms(center, feature_names, n: int = 5) -> list[str]:
    indices = center.argsort()[-n:][::-1]
    return [feature_names[i] for i in indices]


async def run_clustering(posts: list[Post]) -> list[SignalCluster]:
    """
    Cluster posts by textual similarity and persist SignalClusters to DB.

    Extracts text + metadata from posts before any async work so detached
    SQLAlchemy instances (from a closed session) are safe to use.
    Returns the list of newly-created SignalCluster objects.
    """
    if len(posts) < _MIN_POSTS_TO_CLUSTER:
        log.info("Not enough posts to cluster (%d)", len(posts))
        return []

    # Snapshot post data now — safe even if session is already closed
    post_data = [
        {
            "id": p.id,
            "text": p.text_content,
            "canonical_x_url": p.canonical_x_url,
        }
        for p in posts
    ]

    texts = [d["text"] for d in post_data]

    # TF-IDF vectorize
    vectorizer = TfidfVectorizer(
        max_features=500,
        stop_words="english",
        min_df=1,
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(texts)
    feature_names = vectorizer.get_feature_names_out()

    k = _choose_k(len(posts))
    km = KMeans(n_clusters=k, random_state=42, n_init="auto", max_iter=300)
    labels = km.fit_predict(X)

    # Build cluster → member mapping
    cluster_map: dict[int, list[dict]] = {i: [] for i in range(k)}
    for idx, label in enumerate(labels):
        cluster_map[label].append(post_data[idx])

    # Derive per-cluster metadata from KMeans centers
    cluster_terms = [_top_terms(km.cluster_centers_[i], feature_names) for i in range(k)]

    async with get_session() as db:
        created: list[SignalCluster] = []

        for cluster_idx in range(k):
            members = cluster_map[cluster_idx]
            if not members:
                continue

            terms = cluster_terms[cluster_idx]
            topic = ", ".join(terms[:3])
            primary_url = members[0]["canonical_x_url"]

            cluster = SignalCluster(
                name=f"Signal: {topic}",
                topic=topic,
                description=f"{len(members)} posts around: {', '.join(terms)}",
                primary_x_url=primary_url,
                post_count=len(members),
            )
            db.add(cluster)
            await db.flush()  # assigns cluster.id

            # Link posts → cluster via association table
            member_ids = [m["id"] for m in members]
            await db.execute(
                post_clusters.insert(),
                [{"post_id": pid, "cluster_id": cluster.id} for pid in member_ids],
            )

            created.append(cluster)

        await db.commit()
        log.info("Clustering complete: %d posts → %d clusters", len(posts), len(created))
        return created
