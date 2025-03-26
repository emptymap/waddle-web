import io
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Generator, List, Tuple

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Episode, JobStatus, ProcessingJob

tests_dir = Path(__file__).resolve().parent

##############################
# MARK: Fixtures
##############################


# https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/#configure-the-in-memory-database
@pytest.fixture(name="session")
def session_fixture() -> Generator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _configure_test_client(app: FastAPI, session: Session) -> TestClient:
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    return TestClient(app)


# https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/#client-fixture
@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient]:
    """
    Create a test client with an overridden session dependency.
    """
    client = _configure_test_client(app, session)
    yield client
    app.dependency_overrides.clear()


def _get_episode_dir(temp_dir_path: Path, episode_id: str) -> Path:
    """
    Get the episode directory path for the prepopulated episode.
    """
    episode_dir = temp_dir_path / "episodes" / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    return episode_dir


def _add_source(episode_dir: Path) -> None:
    """
    Add source WAV files to the episode directory.
    """
    source_dir = episode_dir / "source"
    source_dir.mkdir(exist_ok=True)

    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    sample_wav = source_dir / "sample.wav"
    sample_wav.write_bytes(original_wav.read_bytes())


def _add_preprocessed(episode_dir: Path) -> None:
    """
    Add preprocessed files to the episode directory.
    """
    preprocessed_dir = episode_dir / "preprocessed"
    preprocessed_dir.mkdir(exist_ok=True)

    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    preprocessed_wav = preprocessed_dir / "preprocessed_sample.wav"
    preprocessed_wav.write_bytes(original_wav.read_bytes())

    srt_file = preprocessed_dir / "transcript.srt"
    with open(srt_file, "w") as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\nThis is a sample transcript.\n\n")
        f.write("2\n00:00:05,500 --> 00:00:10,000\nFor testing purposes only.\n\n")


def _add_edited(episode_dir: Path) -> None:
    """
    Add edited files to the episode directory.
    """
    edited_dir = episode_dir / "edited"
    edited_dir.mkdir(exist_ok=True)

    # Add edited audio file
    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    edited_wav = edited_dir / "edited_sample.wav"
    edited_wav.write_bytes(original_wav.read_bytes())

    combined_wav = episode_dir / "edited-combined.wav"
    combined_wav.write_bytes(original_wav.read_bytes())


def _add_postprocessed(episode_dir: Path) -> None:
    """
    Add postprocessed files to the episode directory.
    """
    postprocessed_dir = episode_dir / "postprocessed"
    postprocessed_dir.mkdir(exist_ok=True)

    # Add postprocessed audio file
    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    postprocessed_wav = postprocessed_dir / "combined.wav"
    postprocessed_wav.write_bytes(original_wav.read_bytes())

    # Add postprocessed SRT file
    srt_file = postprocessed_dir / "postprocessed_transcript.srt"
    with open(srt_file, "w") as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\nThis is a postprocessed transcript.\n\n")
        f.write("2\n00:00:05,500 --> 00:00:10,000\nFor testing purposes only.\n\n")


def _add_episode_to_db(
    session: Session,
    episode_id: str,
    preprocess_status: JobStatus = JobStatus.init,
    postprocess_status: JobStatus = JobStatus.init,
    metadata_generation_status: JobStatus = JobStatus.init,
) -> None:
    """
    Add an episode to the database with a given ID.
    """
    episode = Episode(
        uuid=episode_id,
        title="Test Episode",
        preprocess_status=preprocess_status,
        postprocess_status=postprocess_status,
        metadata_generation_status=metadata_generation_status,
    )
    session.add(episode)
    session.commit()


@pytest.fixture(name="preprocessed_client")
def preprocessed_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """
    Create a test client with a pre-populated episode similar to test_create_episode_with_wavs.
    """
    # Create a temporary directory for testing
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        episode_id = "prepopulated-episode"
        episode_dir = _get_episode_dir(temp_dir_path, episode_id)
        _add_source(episode_dir)
        _add_preprocessed(episode_dir)

        _add_episode_to_db(
            session,
            episode_id=episode_id,
            preprocess_status=JobStatus.completed,
        )

        client = _configure_test_client(app, session)
        yield client
        app.dependency_overrides.clear()


@pytest.fixture(name="edited_client")
def edited_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """
    Create a test client with a pre-populated episode that has completed the editing stage.
    """
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        episode_id = "edited-episode"
        episode_dir = _get_episode_dir(temp_dir_path, episode_id)
        _add_source(episode_dir)
        _add_preprocessed(episode_dir)
        _add_edited(episode_dir)

        _add_episode_to_db(
            session,
            episode_id=episode_id,
            preprocess_status=JobStatus.completed,
        )

        client = _configure_test_client(app, session)
        yield client
        app.dependency_overrides.clear()


@pytest.fixture(name="postprocessed_client")
def postprocessed_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """
    Create a test client with a pre-populated episode that has completed the postprocessing stage.
    """
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        episode_id = "postprocessed-episode"
        episode_dir = _get_episode_dir(temp_dir_path, episode_id)
        _add_source(episode_dir)
        _add_preprocessed(episode_dir)
        _add_edited(episode_dir)
        _add_postprocessed(episode_dir)

        _add_episode_to_db(
            session,
            episode_id=episode_id,
            preprocess_status=JobStatus.completed,
            postprocess_status=JobStatus.completed,
        )

        client = _configure_test_client(app, session)
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


def test_get_edited_combined_audio(edited_client: TestClient) -> None:
    """Test retrieving edited combined audio for a pre-populated episode."""
    episodes = edited_client.get("/v1/episodes/").json()
    assert len(episodes) > 0
    episode_id = episodes[0]["uuid"]

    response = edited_client.get(f"/v1/episodes/{episode_id}/edited-audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0


def test_apply_audio_edits_invalid_episode(edited_client: TestClient) -> None:
    """Test applying audio edits to a non-existent episode."""
    response = edited_client.post("/v1/episodes/nonexistent-id/audio-edits")
    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"


def test_apply_audio_edits_preprocessing_incomplete(session: Session, edited_client: TestClient) -> None:
    """Test applying audio edits when preprocessing is not complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = edited_client.post(f"/v1/episodes/{episode_id}/audio-edits")
    assert response.status_code == 400

    response = edited_client.get(f"/v1/episodes/{episode_id}/edited-audio")
    assert response.status_code == 400


def test_get_edited_audio_not_found(edited_client: TestClient) -> None:
    """Test getting edited audio for a non-existent episode."""
    response = edited_client.get("/v1/episodes/nonexistent-id/edited-audio")
    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"


#####################################
# MARK: Postprocessing tests
#####################################


def test_get_postprocessed_audio(postprocessed_client: TestClient) -> None:
    """Test retrieving postprocessed audio for a pre-populated episode."""
    episodes = postprocessed_client.get("/v1/episodes/").json()
    assert len(episodes) > 0
    episode_id = episodes[0]["uuid"]

    response = postprocessed_client.get(f"/v1/episodes/{episode_id}/postprocessed-audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0


def test_postprocess_invalid_episode(postprocessed_client: TestClient) -> None:
    """Test initiating postprocessing for a non-existent episode."""
    response = postprocessed_client.post("/v1/episodes/nonexistent-id/postprocess")
    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"

    response = postprocessed_client.get("/v1/episodes/nonexistent-id/postprocessed-audio")
    assert response.status_code == 404
    assert response.json()["detail"] == "Episode not found"


def test_postprocess_preprocessing_incomplete(session: Session, postprocessed_client: TestClient) -> None:
    """Test initiating postprocessing when preprocessing is not complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = postprocessed_client.post(f"/v1/episodes/{episode_id}/postprocess")
    assert response.status_code == 400
    assert "Episode preprocessing is not completed" in response.json()["detail"]

    response = postprocessed_client.get(f"/v1/episodes/{episode_id}/postprocessed-audio")
    assert response.status_code == 400


##################################
# MARK: Episode creation tests
##################################
def test_process_all(session: Session, client: TestClient, monkeypatch: MonkeyPatch) -> None:
    """Test creating a new episode with multiple WAV files and wait for preprocessing to complete."""

    with TemporaryDirectory() as temp_dir:
        monkeypatch.setattr("app.v1.router.app_dir", Path(temp_dir))

        wav_dir = Path("tests/ep0")
        assert wav_dir.exists(), f"Test directory {wav_dir} does not exist"

        ref_file = next(wav_dir.glob("GMT*.wav"))
        spk_files = sorted([f for f in wav_dir.glob("*.wav") if not f.name.startswith("GMT")])
        wav_files = [ref_file, spk_files[0]]

        files: List[Tuple[str, Tuple[str, BinaryIO, str]]] = []
        for wav_path in wav_files:
            with open(wav_path, "rb") as f:
                wav_content = f.read()
            files.append(("files", (wav_path.name, io.BytesIO(wav_content), "audio/wav")))

        # Preprocess
        response = client.post("/v1/episodes/", files=files, data={"title": "Test Episode with WAVs"})
        assert response.status_code == 201

        response_data = client.get("/v1/episodes").json()
        assert len(response_data) == 1

        data = response_data[0]
        assert data["title"] == "Test Episode with WAVs"
        assert data["preprocess_status"] == JobStatus.completed

        episode_dir = Path(temp_dir) / "episodes" / data["uuid"]
        assert episode_dir.exists()

        source_dir = episode_dir / "source"
        saved_files = list(source_dir.glob("*.wav"))
        assert len(saved_files) == len(wav_files)

        # Get the processing job
        jobs = session.exec(select(ProcessingJob).where(ProcessingJob.episode_id == data["uuid"])).all()
        assert len(jobs) >= 1
        job = jobs[0]
        assert job is not None
        assert job.status == JobStatus.completed

        preprocessed_dir = episode_dir / "preprocessed"
        assert preprocessed_dir.exists()

        preprocessed_files = list(preprocessed_dir.glob("*.wav"))
        assert len(preprocessed_files) == (len(wav_files) - 1)

        transcript_files = list(preprocessed_dir.glob("*.srt"))
        assert len(transcript_files) > 0

        # Edit the audio
        response = client.post(f"/v1/episodes/{data['uuid']}/audio-edits")
        assert response.status_code == 200

        edited_audio_files = list((episode_dir / "edited").glob("*.wav"))
        assert len(edited_audio_files) == (len(wav_files) - 1)

        edited_combined_file = episode_dir / "edited-combined.wav"
        assert edited_combined_file.exists()
        assert edited_combined_file.stat().st_size > 0

        response = client.get(f"/v1/episodes/{data['uuid']}/edited-audio")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert len(response.content) > 0

        # Postprocess
        response = client.post(f"/v1/episodes/{data['uuid']}/postprocess")
        assert response.status_code == 202

        postprocessed_audio_files = list((episode_dir / "postprocessed").glob("*.wav"))
        assert len(postprocessed_audio_files) > 0
        assert postprocessed_audio_files[0].stat().st_size > 0

        postprocessed_srt_files = list((episode_dir / "postprocessed").glob("*.srt"))
        assert len(postprocessed_srt_files) > 0
