from pathlib import Path

import pytest
from synthetic import write_nano

from cmsopen.ingestion import EventCollection, open_events


@pytest.fixture
def nano_file(tmp_path: Path) -> Path:
    """Minimal synthetic file: a few muon and electron fields, triggers, event IDs."""
    return write_nano(tmp_path / "nano.root")


@pytest.fixture
def full_nano_file(tmp_path: Path) -> Path:
    """Synthetic file that also has every default muon and electron branch."""
    return write_nano(tmp_path / "nano_full.root", full=True)


@pytest.fixture
def events(nano_file: Path) -> EventCollection:
    with open_events(nano_file) as ev:
        yield ev
