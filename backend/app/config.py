"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    num_channels: int = 40
    k_paths: int = 5
    max_services: int = 300
    telemetry_interval_s: float = 2.0
    telemetry_history: int = 90
    osnr_alarm_threshold_db: float = 15.0
    high_utilization_threshold: float = 0.8
    impairment_probability: float = 0.002
    rate_limit_per_minute: int = 120
    seed_demo_services: bool = True
    static_dir: Path | None = None
    cors_origins: list[str] = field(default_factory=list)
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        static = os.getenv("STATIC_DIR")
        origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
        return cls(
            num_channels=_env_int("NUM_CHANNELS", 40),
            k_paths=_env_int("K_PATHS", 5),
            max_services=_env_int("MAX_SERVICES", 300),
            telemetry_interval_s=_env_float("TELEMETRY_INTERVAL_S", 2.0),
            rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", 120),
            seed_demo_services=os.getenv("SEED_DEMO_SERVICES", "true").lower() != "false",
            static_dir=Path(static) if static else None,
            cors_origins=origins,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
