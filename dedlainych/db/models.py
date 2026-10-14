from datetime import date, datetime, time, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    group_code: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (CheckConstraint("subgroup IN (1, 2)", name="ck_user_subgroup"),)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    subgroup: Mapped[int] = mapped_column(Integer, default=1)
    notify_time: Mapped[time] = mapped_column(Time, default=time(20))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Yakutsk")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    urgent_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    registered: Mapped[bool] = mapped_column(Boolean, default=False)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("group_code", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_code: Mapped[str] = mapped_column(String(80), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    label: Mapped[str] = mapped_column(String(200), default="Ручной импорт")


class Lesson(Base):
    __tablename__ = "schedule_lessons"
    __table_args__ = (
        UniqueConstraint("group_code", "date", "start", "subject_id", "subgroup"),
        CheckConstraint("subgroup IN (0, 1, 2)", name="ck_lesson_subgroup"),
        CheckConstraint('"end" > start', name="ck_lesson_time"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"))
    group_code: Mapped[str] = mapped_column(String(80), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    week: Mapped[int | None] = mapped_column(Integer)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    teacher: Mapped[str] = mapped_column(String(200), default="")
    room: Mapped[str] = mapped_column(String(100), default="")
    subgroup: Mapped[int] = mapped_column(Integer, default=0)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(500), default="")


class ConnectedChat(Base):
    __tablename__ = "connected_chats"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    group_code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")


class Source(Base):
    __tablename__ = "homework_sources"
    __table_args__ = (UniqueConstraint("chat_id", "message_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Homework(Base):
    __tablename__ = "homework"
    __table_args__ = (
        Index("ix_homework_group_due", "group_code", "due"),
        CheckConstraint("subgroup IN (0, 1, 2)", name="ck_homework_subgroup"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'superseded', 'rejected')", name="ck_homework_status"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    group_code: Mapped[str] = mapped_column(String(80), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("homework_sources.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    due: Mapped[date | None] = mapped_column(Date)
    subgroup: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Attachment(Base):
    __tablename__ = "homework_attachments"
    __table_args__ = (UniqueConstraint("source_id", "file_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("homework_sources.id"), index=True)
    file_id: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255), default="")


class Completion(Base):
    __tablename__ = "homework_completion"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    homework_id: Mapped[int] = mapped_column(ForeignKey("homework.id", ondelete="CASCADE"), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationHistory(Base):
    __tablename__ = "notification_history"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="claimed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Admin(Base):
    __tablename__ = "admins"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)


class ProcessingLog(Base):
    __tablename__ = "ai_processing_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("homework_sources.id"))
    provider: Mapped[str] = mapped_column(String(30))
    count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
