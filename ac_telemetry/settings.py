"""Load capture profiles and runtime settings.

Named profiles (`pi2b`, `pi5`) keep board-specific caps out of business logic
so a later Pi 5 upgrade is a config change, not a rewrite.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BackendName = Literal["mock", "v4l2"]
ProfileName = Literal["pi2b", "pi5"]


class CaptureProfile(BaseModel):
    """Resolution/FPS request plus hard caps for a board class."""

    name: str
    width: int
    height: int
    fps: float
    max_width: int
    max_height: int
    max_fps: float

    def capped(self) -> CaptureProfile:
        """Clamp requested size/FPS to profile hard caps (Pi 2B safety)."""
        return self.model_copy(
            update={
                "width": min(self.width, self.max_width),
                "height": min(self.height, self.max_height),
                "fps": min(self.fps, self.max_fps),
            }
        )


class Settings(BaseSettings):
    """Runtime settings from YAML + environment overrides."""

    model_config = SettingsConfigDict(
        env_prefix="AC_TELEMETRY_",
        env_file=".env",
        extra="ignore",
    )

    profile: ProfileName = "pi2b"
    backend: BackendName = "mock"
    device: str = "/dev/video0"
    host: str = "0.0.0.0"
    port: int = 8741
    data_dir: Path = Path("data/sessions")

    # Filled from YAML profiles after load
    profiles: dict[str, CaptureProfile] = Field(default_factory=dict)

    def active_profile(self) -> CaptureProfile:
        if self.profile not in self.profiles:
            raise KeyError(f"Unknown capture profile: {self.profile!r}")
        return self.profiles[self.profile].capped()


def _repo_default_yaml() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "default.yaml"


def _parse_profiles(raw: dict[str, Any]) -> dict[str, CaptureProfile]:
    out: dict[str, CaptureProfile] = {}
    for name, body in (raw.get("profiles") or {}).items():
        out[name] = CaptureProfile(name=name, **body)
    return out


def _builtin_profiles() -> dict[str, CaptureProfile]:
    """Safe defaults if YAML is missing — Pi 2B caps stay foremost."""
    return {
        "pi2b": CaptureProfile(
            name="pi2b",
            width=1280,
            height=720,
            fps=10,
            max_width=1280,
            max_height=720,
            max_fps=15,
        ),
        "pi5": CaptureProfile(
            name="pi5",
            width=1920,
            height=1080,
            fps=30,
            max_width=1920,
            max_height=1080,
            max_fps=60,
        ),
    }


def load_settings(config_path: Path | None = None) -> Settings:
    """Merge YAML defaults with env overrides."""
    import os

    path = config_path or Path(os.environ.get("AC_TELEMETRY_CONFIG", str(_repo_default_yaml())))
    data: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    profiles = _builtin_profiles()
    profiles.update(_parse_profiles(data))

    # Env overrides via pydantic for scalar fields; re-apply after YAML base.
    env_settings = Settings()
    return Settings(
        profile=env_settings.profile if "AC_TELEMETRY_PROFILE" in os.environ else data.get("profile", "pi2b"),
        backend=env_settings.backend if "AC_TELEMETRY_BACKEND" in os.environ else data.get("backend", "mock"),
        device=env_settings.device if "AC_TELEMETRY_DEVICE" in os.environ else data.get("device", "/dev/video0"),
        host=env_settings.host if "AC_TELEMETRY_HOST" in os.environ else data.get("host", "0.0.0.0"),
        port=env_settings.port if "AC_TELEMETRY_PORT" in os.environ else int(data.get("port", 8741)),
        data_dir=(
            env_settings.data_dir
            if "AC_TELEMETRY_DATA_DIR" in os.environ
            else Path(data.get("data_dir", "data/sessions"))
        ),
        profiles=profiles,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
