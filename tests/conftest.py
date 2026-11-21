import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost/test?sslmode=disable",
)

import pytest

from app import create_app


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        DATABASE_URL="postgresql://test:test@localhost/test?sslmode=disable",
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()
