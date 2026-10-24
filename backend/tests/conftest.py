from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.controller import NetworkController
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(seed_demo_services=False, impairment_probability=0.0, rate_limit_per_minute=0)


@pytest.fixture
def ctl(settings: Settings) -> NetworkController:
    return NetworkController(settings, rng=random.Random(7))


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
