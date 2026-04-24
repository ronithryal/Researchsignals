"""
DeFi Signal Terminal Database Models

Core entities:
- Account: X/Twitter user accounts being monitored
- Protocol: DeFi protocols and projects
- Post: Individual X/Twitter posts
- SignalCluster: Groups of related posts forming research signals
- CoverageProfile: Protocol-specific enrichment config and cache
- AlertRule: User-defined alert triggers
- IngestionRun: Timestamped ingestion batch tracking
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Table,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

# Association table for many-to-many Post ↔ SignalCluster
post_clusters = Table(
    "post_clusters",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("cluster_id", Integer, ForeignKey("signal_clusters.id", ondelete="CASCADE"), primary_key=True),
)


class Account(Base):
    """X/Twitter accounts being monitored for research signals"""

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    x_id = Column(String(255), unique=True, nullable=False)
    username = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    follower_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    posts = relationship("Post", back_populates="account", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_accounts_x_id", "x_id"),
        Index("ix_accounts_username", "username"),
        Index("ix_accounts_is_active", "is_active"),
    )


class Protocol(Base):
    """DeFi protocols and projects being tracked"""

    __tablename__ = "protocols"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    symbol = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    coverage_profiles = relationship("CoverageProfile", back_populates="protocol", cascade="all, delete-orphan")
    alert_rules = relationship("AlertRule", back_populates="protocol", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_protocols_name", "name"),
        Index("ix_protocols_is_active", "is_active"),
    )


class Post(Base):
    """Individual X/Twitter posts containing DeFi research signals"""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    x_id = Column(String(255), unique=True, nullable=False, index=True)
    canonical_x_url = Column(String(500), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    text_content = Column(Text, nullable=False)
    engagement_score = Column(Float, default=0.0)
    likes_count = Column(Integer, default=0)
    retweets_count = Column(Integer, default=0)
    replies_count = Column(Integer, default=0)
    posted_at = Column(DateTime, nullable=False)
    ingested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    account = relationship("Account", back_populates="posts")
    cluster_assignments = relationship("SignalCluster", secondary=post_clusters, back_populates="posts")

    __table_args__ = (
        Index("ix_posts_x_id", "x_id"),
        Index("ix_posts_canonical_x_url", "canonical_x_url"),
        Index("ix_posts_account_id", "account_id"),
        Index("ix_posts_posted_at", "posted_at"),
        Index("ix_posts_ingested_at", "ingested_at"),
    )


class SignalCluster(Base):
    """Groups of related posts representing DeFi research signals"""

    __tablename__ = "signal_clusters"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    primary_x_url = Column(String(500), nullable=False, index=True)
    topic = Column(String(255), nullable=True, index=True)
    research_alpha_score = Column(Float, default=0.0, index=True)
    confidence_score = Column(Float, default=0.0)
    post_count = Column(Integer, default=0)
    is_archived = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    posts = relationship(
        "Post",
        secondary=post_clusters,
        back_populates="cluster_assignments",
    )

    __table_args__ = (
        Index("ix_signal_clusters_primary_x_url", "primary_x_url"),
        Index("ix_signal_clusters_topic", "topic"),
        Index("ix_signal_clusters_research_alpha_score", "research_alpha_score"),
        Index("ix_signal_clusters_is_archived", "is_archived"),
    )


class CoverageProfile(Base):
    """Protocol-specific enrichment configuration and cache"""

    __tablename__ = "coverage_profiles"

    id = Column(Integer, primary_key=True)
    protocol_id = Column(Integer, ForeignKey("protocols.id"), nullable=False, unique=True, index=True)
    enrichment_config = Column(Text, nullable=True)
    last_enriched_at = Column(DateTime, nullable=True)
    cache_ttl_seconds = Column(Integer, default=21600)  # 6 hours
    is_enabled = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    protocol = relationship("Protocol", back_populates="coverage_profiles")

    __table_args__ = (
        Index("ix_coverage_profiles_protocol_id", "protocol_id"),
        Index("ix_coverage_profiles_is_enabled", "is_enabled"),
    )


class AlertRule(Base):
    """User-defined alert triggers based on signal characteristics"""

    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True)
    protocol_id = Column(Integer, ForeignKey("protocols.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    alpha_score_threshold = Column(Float, default=0.0)
    confidence_threshold = Column(Float, default=0.0)
    post_count_threshold = Column(Integer, default=1)
    is_active = Column(Boolean, default=True, index=True)
    notification_channel = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    protocol = relationship("Protocol", back_populates="alert_rules")

    __table_args__ = (
        Index("ix_alert_rules_protocol_id", "protocol_id"),
        Index("ix_alert_rules_is_active", "is_active"),
    )


class IngestionRun(Base):
    """Timestamped ingestion batch tracking for audit and recovery"""

    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)  # "apify", "xapi", etc.
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    posts_ingested = Column(Integer, default=0)
    posts_new = Column(Integer, default=0)
    posts_updated = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    status = Column(String(50), default="in_progress", index=True)  # "in_progress", "completed", "failed"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ingestion_runs_source", "source"),
        Index("ix_ingestion_runs_started_at", "started_at"),
        Index("ix_ingestion_runs_status", "status"),
    )
