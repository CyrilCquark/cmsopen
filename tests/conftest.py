from pathlib import Path

import pytest
from synthetic import write_nano

from cmsopen.ingestion import EventCollection, open_events

# Per-test time limits (pytest-timeout, "signal" method: a test over its limit fails with a traceback and the run
# goes on). A fit regression once made the slow pull tests grind for over an hour; with these limits it fails within
# minutes. SLOW_TEST_TIMEOUT is well above the slowest normal test (recorded in dev/benchmarks.md, prompt 8).
SLOW_TEST_TIMEOUT = 300
FAST_TEST_TIMEOUT = 120


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Give every test without its own ``timeout`` marker the limit of its class (slow or not)."""
    for item in items:
        if item.get_closest_marker("timeout") is None:
            limit = SLOW_TEST_TIMEOUT if item.get_closest_marker("slow") else FAST_TEST_TIMEOUT
            item.add_marker(pytest.mark.timeout(limit, method="signal"))


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
