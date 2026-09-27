"""Load capture profiles, ROI templates, and runtime settings.

Named profiles (`pi2b`, `pi5`) keep board-specific caps out of business logic
so a later Pi 5 upgrade is a config change, not a rewrite. Missing ROI keys
disable that signal rather than failing the whole service.
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
LapTimeReaderName = Literal["mock", "tesseract"]
LapTimeMode = Literal["last_lap", "current_timer"]


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


class RoiRect(BaseModel):
    """Pixel rectangle for a HUD signal (top-left origin)."""

    x: int
    y: int
    width: int
    height: int


class LapTimeDetectSettings(BaseModel):
    """Per-signal options for the lap_time reader."""

    reader: LapTimeReaderName = "mock"
    mode: LapTimeMode = "last_lap"
    # Mock only: how often a synthetic completed lap appears.
    mock_interval_seconds: float = 45.0
    # current_timer: ignore short segments when detecting a reset.
    min_lap_ms: int = 30_000
    reset_slack_ms: int = 5_000


class DetectSettings(BaseModel):
    """Low-FPS detection budget — kept separate from capture FPS."""

    enabled: bool = True
    fps: float = 2.0
    debounce_reads: int = 2
    drop_under_pressure: bool = True
    lap_time: LapTimeDetectSettings = Field(default_factory=LapTimeDetectSettings)


class Settings(BaseSettings):
    """Runtime settings from YAML + environment overrides."""

    model_config = SettingsConfigDict(
        env_prefix="AC_TELEMETRY_",
        env_file=".env",
        extra="ignore",
    )

    profile: ProfileName = "pi2b"
    backend: BackendName = "v4l2"
    device: str = "/dev/video0"
    # Prefer MJPEG on UVC devices (lower USB/CPU than raw YUYV on Pi 2B).
    prefer_mjpeg: bool = True
    host: str = "0.0.0.0"
    port: int = 8741
    data_dir: Path = Path("data/sessions")

    # Filled from YAML profiles after load
    profiles: dict[str, CaptureProfile] = Field(default_factory=dict)
    rois: dict[str, RoiRect] = Field(default_factory=dict)
    detect: DetectSettings = Field(default_factory=DetectSettings)

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


def _parse_rois(raw: dict[str, Any]) -> dict[str, RoiRect]:
    out: dict[str, RoiRect] = {}
    for name, body in (raw.get("rois") or {}).items():
        if not isinstance(body, dict):
            continue
        out[name] = RoiRect(**body)
    return out


def _parse_detect(raw: dict[str, Any]) -> DetectSettings:
    body = raw.get("detect") or {}
    if not isinstance(body, dict):
        return DetectSettings()
    lap_body = body.get("lap_time") or {}
    if not isinstance(lap_body, dict):
        lap_body = {}
    lap = LapTimeDetectSettings(**{
        k: lap_body[k]
        for k in (
            "reader",
            "mode",
            "mock_interval_seconds",
            "min_lap_ms",
            "reset_slack_ms",
        )
        if k in lap_body
    })
    return DetectSettings(
        enabled=bool(body.get("enabled", True)),
        fps=float(body.get("fps", 2.0)),
        debounce_reads=int(body.get("debounce_reads", 2)),
        drop_under_pressure=bool(body.get("drop_under_pressure", True)),
        lap_time=lap,
    )


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
    rois = _parse_rois(data)
    detect = _parse_detect(data)

    # Env overrides via pydantic for scalar fields; re-apply after YAML base.
    env_settings = Settings()
    return Settings(
        profile=env_settings.profile if "AC_TELEMETRY_PROFILE" in os.environ else data.get("profile", "pi2b"),
        backend=env_settings.backend if "AC_TELEMETRY_BACKEND" in os.environ else data.get("backend", "v4l2"),
        device=env_settings.device if "AC_TELEMETRY_DEVICE" in os.environ else data.get("device", "/dev/video0"),
        prefer_mjpeg=(
            env_settings.prefer_mjpeg
            if "AC_TELEMETRY_PREFER_MJPEG" in os.environ
            else bool(data.get("prefer_mjpeg", True))
        ),
        host=env_settings.host if "AC_TELEMETRY_HOST" in os.environ else data.get("host", "0.0.0.0"),
        port=env_settings.port if "AC_TELEMETRY_PORT" in os.environ else int(data.get("port", 8741)),
        data_dir=(
            env_settings.data_dir
            if "AC_TELEMETRY_DATA_DIR" in os.environ
            else Path(data.get("data_dir", "data/sessions"))
        ),
        profiles=profiles,
        rois=rois,
        detect=detect,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
