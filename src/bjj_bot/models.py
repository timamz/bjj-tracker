from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Belt(StrEnum):
    WHITE = "white"
    BLUE = "blue"
    PURPLE = "purple"
    BROWN = "brown"
    BLACK = "black"
    CORAL = "coral"
    RED_WHITE = "red_white"
    RED = "red"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    progress: Mapped["AthleteProgress"] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[list["TrainingSession"]] = relationship(back_populates="user")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="user")
    arsenal_moves: Mapped[list["ArsenalMove"]] = relationship(back_populates="user")


class AthleteProgress(Base):
    __tablename__ = "athlete_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    belt: Mapped[str] = mapped_column(String(16), default=Belt.WHITE.value)
    stripes: Mapped[int] = mapped_column(Integer, default=0)
    competitor: Mapped[bool] = mapped_column(Integer, default=False, server_default="0")
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="progress")


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    __table_args__ = (Index("ix_training_sessions_user_date", "user_id", "session_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="sessions")
    practiced_moves: Mapped[list["SessionPracticedMove"]] = relationship(back_populates="session")


class Promotion(Base):
    __tablename__ = "promotions"
    __table_args__ = (Index("ix_promotions_user_date", "user_id", "promotion_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    promotion_date: Mapped[date] = mapped_column(Date)
    belt: Mapped[str] = mapped_column(String(16))
    stripes: Mapped[int] = mapped_column(Integer)
    session_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="promotions")


class ArsenalCategory(Base):
    __tablename__ = "arsenal_categories"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("arsenal_categories.code"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ArsenalMove(Base):
    __tablename__ = "arsenal_moves"
    __table_args__ = (Index("ix_arsenal_moves_user_name", "user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category_code: Mapped[str] = mapped_column(ForeignKey("arsenal_categories.code"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="arsenal_moves")
    tags: Mapped[list["MoveTag"]] = relationship(back_populates="move", cascade="all, delete-orphan")


class MoveTag(Base):
    __tablename__ = "move_tags"
    __table_args__ = (UniqueConstraint("move_id", "value", name="uq_move_tag_value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("arsenal_moves.id"))
    value: Mapped[str] = mapped_column(String(64))

    move: Mapped[ArsenalMove] = relationship(back_populates="tags")


class SessionPracticedMove(Base):
    __tablename__ = "session_practiced_moves"
    __table_args__ = (UniqueConstraint("session_id", "move_id", name="uq_session_move"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    move_id: Mapped[int] = mapped_column(ForeignKey("arsenal_moves.id"))

    session: Mapped[TrainingSession] = relationship(back_populates="practiced_moves")

