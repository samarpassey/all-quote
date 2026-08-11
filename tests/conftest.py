import pytest

from tests.fixture_server import FixtureServer


@pytest.fixture(scope="session")
def fixture_server():
    server = FixtureServer()
    yield server
    server.shutdown()
