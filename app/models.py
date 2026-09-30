from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pydantic import BaseModel, Field, field_validator

def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class ProjectInput(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    product_name: str = Field(min_length=1,max_length=200)
    source_url: str = Field(min_length=1,max_length=2000)
    benefits: str = Field(default="",max_length=5000)
    target_audience: str = Field(default="",max_length=500)
    language: str = Field(default="th",max_length=30)
    tone: str = Field(default="friendly",max_length=100)

    @field_validator("name","product_name")
    @classmethod
    def not_blank(cls,v):
        if not v.strip():
            raise ValueError("Name must not be blank")
        return v

    @field_validator("source_url")
    @classmethod
    def safe_url(cls,v):
        u=urlsplit(v)
        if u.scheme not in ("http","https") or not u.hostname or u.username or u.password:
            raise ValueError("Source URL must be a public http(s) URL without credentials")
        return v

class Project(Base):
    __tablename__="projects"
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=lambda:uuid4().hex)
    name: Mapped[str]
    product_name: Mapped[str]
    source_url: Mapped[str]=mapped_column(Text)
    benefits: Mapped[str]=mapped_column(Text,default="")
    target_audience: Mapped[str]=mapped_column(default="")
    language: Mapped[str]=mapped_column(default="th")
    tone: Mapped[str]=mapped_column(default="friendly")
    status: Mapped[str]=mapped_column(default="draft")
    created_at: Mapped[datetime]=mapped_column(default=now)
    updated_at: Mapped[datetime]=mapped_column(default=now,onupdate=now)
    output_dir: Mapped[str]=mapped_column(default="")
    brief: Mapped[str]=mapped_column(Text,default="")
    assembled_current: Mapped[bool]=mapped_column(default=False)
    facts_approved: Mapped[bool]=mapped_column(default=False)
    prompts_approved: Mapped[bool]=mapped_column(default=False)
    test_approved: Mapped[bool]=mapped_column(default=False)
    review_checklist: Mapped[str]=mapped_column(Text,default="[]")
    error_message: Mapped[str]=mapped_column(Text,default="")
    voiceover_path: Mapped[str]=mapped_column(default="")
    subtitle_path: Mapped[str]=mapped_column(default="")

class ProductFact(Base):
    __tablename__="product_facts"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(ForeignKey("projects.id"))
    fact: Mapped[str]=mapped_column(Text)
    source: Mapped[str]=mapped_column(Text,default="")
    verification_status: Mapped[str]=mapped_column(default="unverified")
    notes: Mapped[str]=mapped_column(Text,default="")
    approved: Mapped[bool]=mapped_column(default=False)

class Shot(Base):
    __tablename__="shots"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(ForeignKey("projects.id"))
    shot_number: Mapped[int]
    role: Mapped[str]
    prompt: Mapped[str]=mapped_column(Text)
    negative_prompt: Mapped[str]=mapped_column(Text,default="")
    status: Mapped[str]=mapped_column(default="draft")
    clip_path: Mapped[str]=mapped_column(default="")
    error_message: Mapped[str]=mapped_column(Text,default="")
    operation_id: Mapped[str]=mapped_column(default="")
    duration_seconds: Mapped[float]=mapped_column(default=8)

class GenerationJob(Base):
    __tablename__="generation_jobs"
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=lambda:uuid4().hex)
    project_id: Mapped[str]=mapped_column(ForeignKey("projects.id"))
    shot_id: Mapped[int]=mapped_column(ForeignKey("shots.id"))
    provider: Mapped[str]
    model: Mapped[str]
    status: Mapped[str]=mapped_column(default="queued")
    operation_id: Mapped[str]=mapped_column(default="")
    estimated_cost: Mapped[float | None]=mapped_column(default=None)
    actual_cost_if_available: Mapped[float | None]=mapped_column(default=None)
    retry_count: Mapped[int]=mapped_column(default=0)
    error_message: Mapped[str]=mapped_column(Text,default="")
    created_at: Mapped[datetime]=mapped_column(default=now)
    completed_at: Mapped[datetime | None]=mapped_column(default=None)

class QCReport(Base):
    __tablename__="qc_reports"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(ForeignKey("projects.id"))
    file_path: Mapped[str]
    has_video: Mapped[bool]
    has_audio: Mapped[bool]
    width: Mapped[int]
    height: Mapped[int]
    duration: Mapped[float]
    portrait: Mapped[bool]
    ffprobe_ok: Mapped[bool]
    visual_review_required: Mapped[bool]=mapped_column(default=True)
    notes: Mapped[str]=mapped_column(Text,default="")

