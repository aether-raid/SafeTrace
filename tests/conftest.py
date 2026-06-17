import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def workspace_tmp():
    root = Path.cwd() / "data" / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
