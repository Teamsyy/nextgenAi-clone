from pathlib import Path
import os
import hashlib
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    output_root: Path = ROOT / "projects"
    database_url: str = ""
    video_provider: Literal["mock", "gflow"] = "mock"
    max_retries: int = Field(default=2, ge=0, le=5)
    operation_timeout: float = Field(default=600, gt=0, le=3600)
    poll_initial_delay: float = Field(default=.25, gt=0, le=30)
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    max_upload_mb: int = Field(default=50, ge=1, le=200)
    veo_model: str = ""
    veo_aspect_ratio: Literal["9:16"] = "9:16"
    veo_resolution: Literal["720p"] = "720p"
    veo_duration_seconds: Literal[8] = 8

    def database(self):
        if self.database_url:
            return self.database_url
        dbdir=self.output_root
        if os.name=="nt" and str(dbdir.resolve()).startswith(chr(92)*2):
            # SQLite locking over the WSL network share is unreliable; media may remain there.
            key=hashlib.sha256(str(dbdir.resolve()).encode()).hexdigest()[:12]
            dbdir=Path(os.environ["LOCALAPPDATA"])/"nextgen-local"/key
        dbdir.mkdir(parents=True,exist_ok=True)
        return "sqlite:///" + (dbdir/"nextgen.db").as_posix()

