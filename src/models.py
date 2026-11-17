import enum
from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class SourceStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    DISABLED = "disabled"
    ERROR = "error"

class MessageStatus(str, enum.Enum):
    RECEIVED = "received"
    PREFILTER_DROPPED = "prefilter_dropped"
    ANALYZED = "analyzed"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    DUPLICATE = "duplicate"
    ERROR = "error"

class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=True)
    status = Column(Enum(SourceStatus), default=SourceStatus.ACTIVE, nullable=False, index=True)
    last_message_id = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    messages = relationship("Message", back_populates="source", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("source_id", "telegram_message_id", name="uq_message_source_tg"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_message_id = Column(BigInteger, nullable=False, index=True)
    text = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(MessageStatus), default=MessageStatus.RECEIVED, nullable=False, index=True)
    error_details = Column(Text, nullable=True)
    source = relationship("Source", back_populates="messages")
    job = relationship("Job", back_populates="message", uselist=False, cascade="all, delete-orphan")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    title = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    company = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True, index=True)
    district = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    salary = Column(String(100), nullable=True)
    currency = Column(String(10), nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    schedule = Column(String(150), nullable=True)
    employment_type = Column(String(100), nullable=True)
    requirements = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    contact = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    score = Column(Integer, nullable=False, default=0)
    grade = Column(String(5), nullable=False, default="C")
    published_message_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    message = relationship("Message", back_populates="job")
    duplicates = relationship("Duplicate", foreign_keys="[Duplicate.duplicate_of]", back_populates="original_job")

class Duplicate(Base):
    __tablename__ = "duplicates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    # job_id: для обычных дублей — Job.id; для отброшенных на этапе Message
    # (без созданного Job) сюда пишется Message.id. Поле без FK — см. pipeline.
    job_id = Column(Integer, nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True)
    duplicate_of = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    similarity = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    original_job = relationship("Job", back_populates="duplicates", foreign_keys=[duplicate_of])
