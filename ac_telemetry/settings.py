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

BackendName = Literal["mock", "v4l2", "file", "video"]
ProfileName = Literal["pi2b", "pi5"]
LapTimeReaderName = Literal["mock", "tesseract", "template", "assetto_corsa"]
LapTimeMode = Literal["last_lap", "current_timer"]


def normalize_backend(name: str) -> BackendName:
    """Map aliases; ``video`` is the same OpenCV file path backend as ``file``."""
    key = (name or "").strip().lower()
    if key == "video":
        return "file"
    if key in ("mock", "v4l2", "file"):
        return key  # type: ignore[return-value]
    raise ValueError(f"Unknown capture backend: {name!r}")


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
    # last_lap: min wall-clock ms between CSV writes (blocks OCR flicker spam).
    # current_timer: ignore short segments when detecting a reset.
    min_lap_ms: int = 30_000
    reset_slack_ms: int = 5_000
    # template / assetto_corsa only — digit PNGs (see templates/lap_time_digits/).
    templates_dir: str = "templates/lap_time_digits/ac_720p"
    match_threshold: float = 0.50


class DetectDebugDumpSettings(BaseModel):
    """Last-detect dump for Pi diagnosis (failure-only by default).

    Keeps one ROI + mask + score table in RAM. Cheap on Pi 2B: overwrite a
    single slot; no continuous JPEG encode in the detect loop.
    """

    # Keep last failure artifacts (recommended). Force via env
    # AC_TELEMETRY_DETECT_DEBUG_DUMP=1/true/yes.
    enabled: bool = True
    # Refresh the dump on successful reads (usually leave false).
    on_success: bool = False
    # 1 = every failure; raise to sample if CPU-sensitive.
    every_n_failures: int = 1
    # Opt-in full-frame copy (larger); prefer request-time /api/debug/frame.jpg.
    include_full_frame: bool = False


class DetectSettings(BaseModel):
    """Low-FPS detection budget — kept separate from capture FPS."""

    enabled: bool = True
    fps: float = 2.0
    debounce_reads: int = 2
    drop_under_pressure: bool = True
    lap_time: LapTimeDetectSettings = Field(default_factory=LapTimeDetectSettings)
    debug_dump: DetectDebugDumpSettings = Field(
        default_factory=DetectDebugDumpSettings
    )


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
    # file / video backend: path to a clip, single image, or OpenCV image-sequence
    # pattern (e.g. /path/frame_%04d.png). Ignored by mock / v4l2.
    file_path: str = ""
    # When True, rewind (or re-open) at EOF so sandbox can run indefinitely.
    loop: bool = True
    host: str = "0.0.0.0"
    port: int = 8741
    data_dir: Path = Path("data/sessions")
    # Where /debug "Save glyph" writes PNG templates cut from the live ROI.
    # Prefer live Pi set (sibling to VLC ac_720p_capture); keep ACC ac_720p intact.
    glyphs_dir: Path = Path("templates/lap_time_digits/ac_720p_pi")
    # Bounded card-native tee from the capture thread (see /api/debug/record/*).
    # On the Pi, point this at ~/ac-telemetry-testdata/card for golden clips.
    record_dir: Path = Path("data/recordings")
    record_default_seconds: float = 60.0
    record_max_seconds: float = 120.0
    # Bound VideoCapture/file open so a missing HDMI signal or stuck V4L2
    # driver cannot block the capture thread (and Ctrl-C joins) for minutes.
    capture_open_timeout_seconds: float = 15.0

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
            "templates_dir",
            "match_threshold",
        )
        if k in lap_body
    })
    dump_body = body.get("debug_dump") or {}
    if not isinstance(dump_body, dict):
        dump_body = {}
    dump = DetectDebugDumpSettings(**{
        k: dump_body[k]
        for k in (
            "enabled",
            "on_success",
            "every_n_failures",
            "include_full_frame",
        )
        if k in dump_body
    })
    # Env flag forces dump on (handy without editing YAML on the Pi).
    import os

    env_flag = os.environ.get("AC_TELEMETRY_DETECT_DEBUG_DUMP", "").strip().lower()
    if env_flag in ("1", "true", "yes", "on"):
        dump = dump.model_copy(update={"enabled": True})
    elif env_flag in ("0", "false", "no", "off"):
        dump = dump.model_copy(update={"enabled": False})
    return DetectSettings(
        enabled=bool(body.get("enabled", True)),
        fps=float(body.get("fps", 2.0)),
        debounce_reads=int(body.get("debounce_reads", 2)),
        drop_under_pressure=bool(body.get("drop_under_pressure", True)),
        lap_time=lap,
        debug_dump=dump,
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
    # Accept either top-level backend or nested capture.source (HITL sandbox docs).
    capture_block = data.get("capture") if isinstance(data.get("capture"), dict) else {}
    raw_backend = (
        env_settings.backend
        if "AC_TELEMETRY_BACKEND" in os.environ
        else data.get("backend")
        or capture_block.get("source")
        or "v4l2"
    )
    backend = normalize_backend(str(raw_backend))
    raw_file_path = (
        env_settings.file_path
        if "AC_TELEMETRY_FILE_PATH" in os.environ
        else data.get("file_path")
        or capture_block.get("file_path")
        or ""
    )
    raw_loop = (
        env_settings.loop
        if "AC_TELEMETRY_LOOP" in os.environ
        else data.get("loop", capture_block.get("loop", True))
    )
    return Settings(
        profile=env_settings.profile if "AC_TELEMETRY_PROFILE" in os.environ else data.get("profile", "pi2b"),
        backend=backend,
        device=env_settings.device if "AC_TELEMETRY_DEVICE" in os.environ else data.get("device", "/dev/video0"),
        prefer_mjpeg=(
            env_settings.prefer_mjpeg
            if "AC_TELEMETRY_PREFER_MJPEG" in os.environ
            else bool(data.get("prefer_mjpeg", True))
        ),
        file_path=str(raw_file_path or ""),
        loop=bool(raw_loop),
        host=env_settings.host if "AC_TELEMETRY_HOST" in os.environ else data.get("host", "0.0.0.0"),
        port=env_settings.port if "AC_TELEMETRY_PORT" in os.environ else int(data.get("port", 8741)),
        data_dir=(
            env_settings.data_dir
            if "AC_TELEMETRY_DATA_DIR" in os.environ
            else Path(data.get("data_dir", "data/sessions"))
        ),
        glyphs_dir=(
            env_settings.glyphs_dir
            if "AC_TELEMETRY_GLYPHS_DIR" in os.environ
            else Path(
                data.get(
                    "glyphs_dir",
                    "templates/lap_time_digits/ac_720p_pi",
                )
            )
        ),
        record_dir=(
            env_settings.record_dir
            if "AC_TELEMETRY_RECORD_DIR" in os.environ
            else Path(data.get("record_dir", "data/recordings"))
        ),
        record_default_seconds=(
            env_settings.record_default_seconds
            if "AC_TELEMETRY_RECORD_DEFAULT_SECONDS" in os.environ
            else float(data.get("record_default_seconds", 60.0))
        ),
        record_max_seconds=(
            env_settings.record_max_seconds
            if "AC_TELEMETRY_RECORD_MAX_SECONDS" in os.environ
            else float(data.get("record_max_seconds", 120.0))
        ),
        capture_open_timeout_seconds=(
            env_settings.capture_open_timeout_seconds
            if "AC_TELEMETRY_CAPTURE_OPEN_TIMEOUT_SECONDS" in os.environ
            else float(data.get("capture_open_timeout_seconds", 15.0))
        ),
        profiles=profiles,
        rois=rois,
        detect=detect,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
