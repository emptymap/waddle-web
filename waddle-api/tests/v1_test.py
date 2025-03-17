import io
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Generator, List, Tuple

import pytest
from _pytest.monkeypatch import MonkeyPatch  # Import the MonkeyPatch type
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Episode, ProcessingJob

tests_dir = Path(__file__).resolve().parent


# https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/#configure-the-in-memory-database
@pytest.fixture(name="session")
def session_fixture() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/#client-fixture
@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient]:
    """
    Create a test client with an overridden session dependency.
    """

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_read_episodes_empty(client: TestClient) -> None:
    """Test reading episodes when the database is empty."""
    response = client.get("/v1/episodes/")
    assert response.status_code == 200
    assert response.json() == []


def test_read_episodes(session: Session, client: TestClient) -> None:
    """Test reading episodes with data in the database."""
    # Create test episodes
    episode_1 = Episode(title="Episode 1")
    episode_2 = Episode(title="Episode 2")
    session.add(episode_1)
    session.add(episode_2)
    session.commit()

    # Test reading episodes
    response = client.get("/v1/episodes/")
    data = response.json()

    assert response.status_code == 200
    assert len(data) == 2
    assert data[0]["title"] == episode_1.title
    assert data[1]["title"] == episode_2.title

    # Test pagination
    response = client.get("/v1/episodes/?offset=1&limit=1")
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == episode_2.title


def test_create_episode_with_wavs(session: Session, client: TestClient, monkeypatch: MonkeyPatch) -> None:
    """Test creating a new episode with multiple WAV files from tests/ep0 directory."""
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setattr("app.v1.router.app_dir", Path(temp_dir))

        wav_dir = Path("tests/ep0")
        assert wav_dir.exists(), f"Test directory {wav_dir} does not exist"

        wav_files = list(wav_dir.glob("*.wav"))
        assert len(wav_files) > 0, f"No WAV files found in {wav_dir}"

        # Prepare files for upload
        files: List[Tuple[str, Tuple[str, BinaryIO, str]]] = []
        for wav_path in wav_files:
            with open(wav_path, "rb") as f:
                wav_content = f.read()
            files.append(("files", (wav_path.name, io.BytesIO(wav_content), "audio/wav")))

        # Make the request with all WAV files
        response = client.post("/v1/episodes/", files=files, data={"title": "Test Episode with WAVs"})

        # Check the response
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Episode with WAVs"
        assert data["preprocessed"] is False

        # Verify that files were saved
        episode_dir = Path(temp_dir) / "episodes" / data["uuid"]
        assert episode_dir.exists()

        # Check if all uploaded files are present in the episode directory
        source_dir = episode_dir / "source"
        saved_files = list(source_dir.glob("*.wav"))
        assert len(saved_files) == len(wav_files)

        # Verify that a preprocessing job was created
        jobs = session.exec(select(ProcessingJob)).all()
        assert len(jobs) >= 1
        job = next((j for j in jobs if j.episode_id == data["uuid"]), None)
        assert job is not None


def test_update_episode(session: Session, client: TestClient) -> None:
    """Test updating an episode."""
    # Create a test episode
    episode = Episode(title="Original Title")
    session.add(episode)
    session.commit()

    # Update the episode
    response = client.patch(f"/v1/episodes/{episode.uuid}", json={"title": "Updated Title"})

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"

    # Verify the database was updated
    updated_episode = session.get(Episode, episode.uuid)
    assert updated_episode is not None
    assert updated_episode.title == "Updated Title"


def test_update_episode_not_found(client: TestClient) -> None:
    """Test updating a non-existent episode."""
    response = client.patch("/v1/episodes/nonexistent-id", json={"title": "Updated Title"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"


def test_delete_episode(session: Session, client: TestClient) -> None:
    """Test deleting an episode."""
    # Create a test episode
    episode = Episode(title="Test Episode")
    session.add(episode)
    session.commit()

    # Delete the episode
    response = client.delete(f"/v1/episodes/{episode.uuid}")

    assert response.status_code == 204

    # Verify the episode was deleted from the database
    deleted_episode = session.get(Episode, episode.uuid)
    assert deleted_episode is None


def test_delete_episode_not_found(client: TestClient) -> None:
    """Test deleting a non-existent episode."""
    response = client.delete("/v1/episodes/nonexistent-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"
