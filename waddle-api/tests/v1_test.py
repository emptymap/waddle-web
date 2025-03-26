import io
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Generator, List, Tuple

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Episode, JobStatus, ProcessingJob

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


@pytest.fixture(name="preprocessed_client")
def preprocessed_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """
    Create a test client with a pre-populated episode similar to test_create_episode_with_wavs.
    """
    # Create a temporary directory for testing
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        # Mock the app_dir to use our temporary directory
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        # First, create the directory structure
        episode_id = "prepopulated-episode"
        episode_dir = temp_dir_path / "episodes" / episode_id
        episode_dir.mkdir(parents=True, exist_ok=True)

        original_wav = tests_dir / "ep0" / "ep12-masa.wav"

        # Create source directory and add sample files
        source_dir = episode_dir / "source"
        source_dir.mkdir(exist_ok=True)
        sample_wav = source_dir / "sample.wav"
        sample_wav.write_bytes(original_wav.read_bytes())

        # Create preprocessed directory and add sample files
        preprocessed_dir = episode_dir / "preprocessed"
        preprocessed_dir.mkdir(exist_ok=True)

        # Create sample preprocessed WAV file
        preprocessed_wav = preprocessed_dir / "preprocessed_sample.wav"
        preprocessed_wav.write_bytes(original_wav.read_bytes())

        # Create sample SRT file
        srt_file = preprocessed_dir / "transcript.srt"
        with open(srt_file, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\nThis is a sample transcript.\n\n")
            f.write("2\n00:00:05,500 --> 00:00:10,000\nFor testing purposes only.\n\n")

        def get_session_override():
            return session

        app.dependency_overrides[get_session] = get_session_override
        client = TestClient(app)

        # Create a test episode with completed preprocessing status
        episode = Episode(uuid=episode_id, title="Prepopulated Test Episode", preprocess_status=JobStatus.completed)
        session.add(episode)
        session.commit()

        yield client
        app.dependency_overrides.clear()


#####################################
# MARK: Episode CRUD operations
#####################################


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
    """Test creating a new episode with multiple WAV files and wait for preprocessing to complete."""

    with TemporaryDirectory() as temp_dir:
        monkeypatch.setattr("app.v1.router.app_dir", Path(temp_dir))

        wav_dir = Path("tests/ep0")
        assert wav_dir.exists(), f"Test directory {wav_dir} does not exist"

        ref_file = next(wav_dir.glob("GMT*.wav"))
        spk_files = sorted([f for f in wav_dir.glob("*.wav") if not f.name.startswith("GMT")])
        wav_files = [ref_file, spk_files[0]]

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

        response_data = client.get("/v1/episodes").json()
        assert len(response_data) == 1

        data = response_data[0]
        assert data["title"] == "Test Episode with WAVs"
        assert data["preprocess_status"] == JobStatus.completed

        # Verify that source files were saved
        episode_dir = Path(temp_dir) / "episodes" / data["uuid"]
        assert episode_dir.exists()

        # Check that source files were saved
        source_dir = episode_dir / "source"
        saved_files = list(source_dir.glob("*.wav"))
        assert len(saved_files) == len(wav_files)

        # Get the processing job
        jobs = session.exec(select(ProcessingJob).where(ProcessingJob.episode_id == data["uuid"])).all()
        assert len(jobs) >= 1
        job = jobs[0]
        assert job is not None
        assert job.status == JobStatus.completed

        # Verify that preprocessed files exist
        preprocessed_dir = episode_dir / "preprocessed"
        assert preprocessed_dir.exists()

        # Check that preprocessed files were generated
        preprocessed_files = list(preprocessed_dir.glob("*.wav"))
        assert len(preprocessed_files) == (len(wav_files) - 1)

        # Check for transcription files if your preprocessor generates them
        transcript_files = list(preprocessed_dir.glob("*.srt"))
        assert len(transcript_files) > 0


def test_read_episode(session: Session, client: TestClient) -> None:
    """Test reading a single episode."""
    # Create a test episode
    episode = Episode(title="Test Episode")
    session.add(episode)
    session.commit()

    # Read the episode
    response = client.get(f"/v1/episodes/{episode.uuid}")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == episode.title


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


#####################################
# MARK: Preprocessed resources: audio files and SRT transcription
#####################################


def test_get_audio_file(preprocessed_client: TestClient) -> None:
    """Test retrieving a specific audio file for a pre-populated episode."""
    # Get the episode from the database
    episodes = preprocessed_client.get("/v1/episodes/").json()
    assert len(episodes) > 0
    episode_id = episodes[0]["uuid"]

    # Get list of audio files
    audio_files_response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audios")
    assert audio_files_response.status_code == 200

    audio_files = audio_files_response.json()
    assert len(audio_files) > 0

    # Test getting the audio file (using exact filename from our fixture)
    file_name = "preprocessed_sample.wav"
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/{file_name}")
    assert response.status_code == 200

    # Verify it's an audio file by checking content type
    assert response.headers["content-type"] == "audio/wav"

    # Test with invalid file name
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/nonexistent.wav")
    assert response.status_code == 404

    # Test with potentially malicious file name
    malicious_filename = urllib.parse.quote("../../../../etc/passwd")
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/{malicious_filename}")
    assert response.status_code != 200


def test_get_transcription(preprocessed_client: TestClient) -> None:
    """Test retrieving SRT transcription for a pre-populated episode."""
    # Get the episode from the database
    episodes = preprocessed_client.get("/v1/episodes/").json()
    assert len(episodes) > 0
    episode_id = episodes[0]["uuid"]

    # Test getting SRT content
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/srt")
    assert response.status_code == 200

    # Verify the SRT content format
    srt_content = response.text
    assert isinstance(srt_content, str)
    assert len(srt_content) > 0

    # Check for expected content from our fixture
    assert "This is a sample transcript." in srt_content
    assert "For testing purposes only." in srt_content

    # Check format of timestamps
    assert "00:00:00,000 --> 00:00:05,000" in srt_content
    assert "00:00:05,500 --> 00:00:10,000" in srt_content


def test_preprocessed_resources_with_invalid_episode_prepopulated(preprocessed_client: TestClient) -> None:
    """Test retrieving preprocessed resources with an invalid episode ID."""
    invalid_id = "nonexistent-id"

    # Test with nonexistent episode ID
    response = preprocessed_client.get(f"/v1/episodes/{invalid_id}/audios")
    assert response.status_code == 404

    response = preprocessed_client.get(f"/v1/episodes/{invalid_id}/audio/file.wav")
    assert response.status_code == 404

    response = preprocessed_client.get(f"/v1/episodes/{invalid_id}/srt")
    assert response.status_code == 404


def test_preprocessed_resources_before_preprocessing_prepopulated(session: Session, preprocessed_client: TestClient) -> None:
    """Test retrieving preprocessed resources for an episode before preprocessing is complete."""
    # Create a new episode with pending preprocessing status
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audios")
    assert response.status_code == 400

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/file.wav")
    assert response.status_code == 400

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/srt")
    assert response.status_code == 400


#####################################
# MARK: Audio editing endpoints tests
#####################################


def test_apply_audio_edits(preprocessed_client: TestClient) -> None:
    """Test applying audio edits to an episode."""
    episodes = preprocessed_client.get("/v1/episodes/").json()
    assert len(episodes) > 0
    episode_id = episodes[0]["uuid"]

    # Apply audio edits
    response = preprocessed_client.post(f"/v1/episodes/{episode_id}/audio-edits")
    assert response.status_code == 200

    # Check that we get a list of file names
    file_names: list[str] = response.json()
    assert isinstance(file_names, list)
    assert len(file_names) > 0

    # Check edited audio file
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/edited-audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0


def test_apply_audio_edits_invalid_episode(preprocessed_client: TestClient) -> None:
    """Test applying audio edits to a non-existent episode."""
    response = preprocessed_client.post("/v1/episodes/nonexistent-id/audio-edits")
    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"


def test_apply_audio_edits_preprocessing_incomplete(session: Session, preprocessed_client: TestClient) -> None:
    """Test applying audio edits when preprocessing is not complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = preprocessed_client.post(f"/v1/episodes/{episode_id}/audio-edits")
    assert response.status_code == 400

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/edited-audio")
    assert response.status_code == 400


def test_get_edited_audio_not_found(preprocessed_client: TestClient) -> None:
    """Test getting edited audio for a non-existent episode."""
    response = preprocessed_client.get("/v1/episodes/nonexistent-id/edited-audio")
    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"
