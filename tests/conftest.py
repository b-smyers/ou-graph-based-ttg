"""Pytest fixtures for create_schedule tests."""

import json
import sys
from pathlib import Path

import pytest

# Add parent directory to path so we can import create_schedule
sys.path.insert(0, str(Path(__file__).parent.parent))

from create_schedule import get_db_credentials, create_driver


@pytest.fixture(scope="session")
def neo4j_driver():
    """Create a live Neo4j driver connection for the test session."""
    uri, auth = get_db_credentials()
    driver = create_driver(uri, auth)
    yield driver
    driver.close()


@pytest.fixture(scope="session")
def neo4j_session(neo4j_driver):
    """Create a live Neo4j session for the test session."""
    session = neo4j_driver.session()
    yield session
    session.close()


@pytest.fixture
def sample_program():
    """Load sample program for tests from live database."""
    sample_path = Path(__file__).parent.parent / "data" / "sample.bs7241.json"
    with open(sample_path, "r") as f:
        return json.load(f)


@pytest.fixture
def fake_course_nodes(neo4j_session):
    """Retrieve real course nodes from live database."""

    def run_query(tx):
        result = tx.run(
            """
            MATCH (course:COURSE)
            RETURN course.code as code, course.name as name, 
                   course.min_credits as min_credits, course.uuid as uuid
            LIMIT 100
            """
        )
        courses = {}
        for record in result:
            code = record.get("code")
            if code:
                courses[code] = {
                    "code": code,
                    "name": record.get("name", ""),
                    "min_credits": record.get("min_credits", 3),
                    "uuid": record.get("uuid", ""),
                }
        return courses

    courses = neo4j_session.execute_read(run_query)
    if not courses:
        raise RuntimeError(
            "No courses found in live database. Please check database connectivity."
        )
    return courses


@pytest.fixture
def sample_course_by_code(fake_course_nodes):
    """Return a course index mapping codes to nodes from live database."""
    return {code.upper(): node for code, node in fake_course_nodes.items()}


@pytest.fixture
def fake_tx(neo4j_session):
    """Create a session-based transaction wrapper for live database queries."""

    class SessionWrapper:
        def __init__(self, session):
            self.session = session

        def run(self, query, **kwargs):
            return self.session.run(query, **kwargs)

    return SessionWrapper(neo4j_session)


@pytest.fixture
def fake_session(neo4j_session):
    """Use the live Neo4j session directly."""
    return neo4j_session


@pytest.fixture
def fake_driver(neo4j_driver):
    """Use the live Neo4j driver directly."""
    return neo4j_driver


@pytest.fixture
def monkeypatch_env(monkeypatch):
    """Monkeypatch environment to disable file logging."""
    monkeypatch.setenv("ENV", "test")
    return monkeypatch
