"""SQLAlchemy models mirroring the AstroGraph SQLite schema — used by Alembic for migrations."""
from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship


class Base(DeclarativeBase):
    """All AstroGraph ORM models inherit from this."""
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)


class QAHistory(Base):
    __tablename__ = "qa_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    citations_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)

    user = relationship("User", backref="qa_history")


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    username = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", backref="auth_tokens")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    entity_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    source_file = Column(String, nullable=False)
    raw_json = Column(Text, nullable=False)


class ImageAsset(Base):
    __tablename__ = "image_assets"

    image_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    source = Column(String, nullable=False)
    ref = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    url = Column(String, nullable=False)
    object_keys_json = Column(Text, nullable=False)
    bucket = Column(String, nullable=False)
