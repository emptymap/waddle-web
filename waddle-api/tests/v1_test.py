import io
import urllib.parse
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Generator, List, Tuple

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Episode, JobStatus, ProcessingJob

tests_dir = Path(__file__).resolve().parent

##############################
# MARK: Helper functions
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
    """Get the episode directory path for the prepopulated episode."""
    episode_dir = temp_dir_path / "episodes" / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    return episode_dir


def _add_source(episode_dir: Path) -> None:
    """Add source WAV files to the episode directory."""
    source_dir = episode_dir / "source"
    source_dir.mkdir(exist_ok=True)

    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    sample_wav = source_dir / "sample.wav"
    sample_wav.write_bytes(original_wav.read_bytes())


def _add_preprocessed(episode_dir: Path) -> None:
    """Add preprocessed files to the episode directory."""
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
    """Add edited files to the episode directory."""
    edited_dir = episode_dir / "edited"
    edited_dir.mkdir(exist_ok=True)

    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    edited_wav = edited_dir / "edited_sample.wav"
    edited_wav.write_bytes(original_wav.read_bytes())

    combined_wav = episode_dir / "edited-combined.wav"
    combined_wav.write_bytes(original_wav.read_bytes())


def _add_postprocessed(episode_dir: Path) -> None:
    """Add postprocessed files to the episode directory."""
    postprocessed_dir = episode_dir / "postprocessed"
    postprocessed_dir.mkdir(exist_ok=True)

    original_wav = tests_dir / "ep0" / "ep12-masa.wav"
    postprocessed_wav = postprocessed_dir / "combined.wav"
    postprocessed_wav.write_bytes(original_wav.read_bytes())

    srt_file = postprocessed_dir / "postprocessed_transcript.srt"
    with open(srt_file, "w") as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\nThis is a postprocessed transcript.\n\n")
        f.write("2\n00:00:05,500 --> 00:00:10,000\nFor testing purposes only.\n\n")


def _add_metadata(episode_dir: Path) -> None:
    """Add metadata files to the episode directory."""
    metadata_dir = episode_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)

    metadata_audio_file = metadata_dir / "metadata_audio.wav"
    metadata_audio_file.write_bytes(b"Dummy audio data for metadata.")

    # Add chapter file
    chapter_file = metadata_dir / "test.chapters.txt"
    with open(chapter_file, "w") as f:
        f.write("- (00:06) Test1\n- (00:12) Test2")

    # Add show notes file
    show_notes_file = metadata_dir / "test.show_notes.md"
    with open(show_notes_file, "w") as f:
        f.write("# Test Episode Show Notes\n\n")
        f.write("## Introduction\n")
        f.write("- Welcoming the guest\n")
        f.write("- Overview of the topics\n\n")
        f.write("## Links\n")
        f.write("- [Example Link](https://example.com)\n")


def _add_export(episode_dir: Path) -> None:
    """Add export files to the episode directory."""
    export_dir = episode_dir / "export"
    export_dir.mkdir(exist_ok=True)
    zip_path = export_dir / "Test Episode.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("dummy.txt", "This is a dummy file for testing.")


def _add_episode_to_db(
    session: Session,
    episode_id: str,
    preprocess_status: JobStatus = JobStatus.init,
    edit_status: JobStatus = JobStatus.init,
    postprocess_status: JobStatus = JobStatus.init,
    metadata_generation_status: JobStatus = JobStatus.init,
    export_status: JobStatus = JobStatus.init,
) -> None:
    """Add an episode to the database with a given ID."""
    episode = Episode(
        uuid=episode_id,
        title="Test Episode",
        preprocess_status=preprocess_status,
        edit_status=edit_status,
        postprocess_status=postprocess_status,
        metadata_generation_status=metadata_generation_status,
        export_status=export_status,
    )
    session.add(episode)
    session.commit()


@pytest.fixture(name="preprocessed_client")
def preprocessed_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """After preprocessed client."""
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
    After edited client.
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
            edit_status=JobStatus.completed,
        )

        client = _configure_test_client(app, session)
        yield client
        app.dependency_overrides.clear()


@pytest.fixture(name="postprocessed_client")
def postprocessed_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """
    After postprocessed client.
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
            edit_status=JobStatus.completed,
            postprocess_status=JobStatus.completed,
        )

        client = _configure_test_client(app, session)
        yield client
        app.dependency_overrides.clear()


@pytest.fixture(name="metadata_client")
def metadata_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """
    After metadata generation client
    """
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        episode_id = "metadata-test-episode"
        episode_dir = _get_episode_dir(temp_dir_path, episode_id)
        _add_source(episode_dir)
        _add_preprocessed(episode_dir)
        _add_edited(episode_dir)
        _add_postprocessed(episode_dir)
        _add_metadata(episode_dir)

        _add_episode_to_db(
            session,
            episode_id=episode_id,
            preprocess_status=JobStatus.completed,
            edit_status=JobStatus.completed,
            postprocess_status=JobStatus.completed,
            metadata_generation_status=JobStatus.completed,
        )

        client = _configure_test_client(app, session)
        yield client
        app.dependency_overrides.clear()


@pytest.fixture(name="export_client")
def export_client_fixture(session: Session, monkeypatch: MonkeyPatch) -> Generator[TestClient]:
    """After export client"""
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        episode_id = "export-test-episode"
        episode_dir = _get_episode_dir(temp_dir_path, episode_id)
        _add_source(episode_dir)
        _add_preprocessed(episode_dir)
        _add_edited(episode_dir)
        _add_postprocessed(episode_dir)
        _add_metadata(episode_dir)
        _add_export(episode_dir)

        _add_episode_to_db(
            session,
            episode_id=episode_id,
            preprocess_status=JobStatus.completed,
            edit_status=JobStatus.completed,
            postprocess_status=JobStatus.completed,
            metadata_generation_status=JobStatus.completed,
            export_status=JobStatus.completed,
        )
        client = _configure_test_client(app, session)
        yield client
        app.dependency_overrides.clear()


def _get_episode_id(target_client: TestClient) -> str:
    episodes = target_client.get("/v1/episodes/").json()
    assert len(episodes) > 0
    episode_id = episodes[0]["uuid"]
    return episode_id


#####################################
# MARK: Episode CRUD operations
#####################################


def test_read_episodes_empty(client: TestClient) -> None:
    """Test reading episodes when the database is empty."""
    response = client.get("/v1/episodes/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_read_episodes(session: Session, client: TestClient) -> None:
    """Test reading episodes with data in the database."""
    episode_1 = Episode(title="Episode 1")
    episode_2 = Episode(title="Episode 2")
    session.add(episode_1)
    session.add(episode_2)
    session.commit()

    response = client.get("/v1/episodes/")
    data = response.json()

    assert response.status_code == status.HTTP_200_OK
    assert len(data) == 2
    assert data[0]["title"] == episode_1.title
    assert data[1]["title"] == episode_2.title

    response = client.get("/v1/episodes/?offset=1&limit=1")
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == episode_2.title


def test_read_episode(session: Session, client: TestClient) -> None:
    """Test reading a single episode."""
    episode = Episode(title="Test Episode")
    session.add(episode)
    session.commit()

    response = client.get(f"/v1/episodes/{episode.uuid}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == episode.title


def test_update_episode(session: Session, client: TestClient) -> None:
    """Test updating an episode."""
    episode = Episode(title="Original Title")
    session.add(episode)
    session.commit()

    response = client.patch(f"/v1/episodes/{episode.uuid}", json={"title": "Updated Title", "editor_state": "new"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["title"] == "Updated Title"

    updated_episode = session.get(Episode, episode.uuid)
    assert updated_episode is not None
    assert updated_episode.title == "Updated Title"


def test_update_episode_not_found(client: TestClient) -> None:
    """Test updating a non-existent episode."""
    response = client.patch("/v1/episodes/nonexistent-id", json={"title": "Updated Title"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"


def test_delete_episode(session: Session, client: TestClient) -> None:
    """Test deleting an episode."""
    episode = Episode(title="Test Episode")
    session.add(episode)
    session.commit()

    response = client.delete(f"/v1/episodes/{episode.uuid}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    deleted_episode = session.get(Episode, episode.uuid)
    assert deleted_episode is None


def test_delete_episode_not_found(client: TestClient) -> None:
    """Test deleting a non-existent episode."""
    response = client.delete("/v1/episodes/nonexistent-id")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"


#####################################
# MARK: Preprocessed resources: audio files and SRT transcription
#####################################


def test_get_audio_file(preprocessed_client: TestClient) -> None:
    """Test retrieving a specific audio file for a pre-populated episode."""
    episode_id = _get_episode_id(preprocessed_client)

    audio_files_response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audios")
    assert audio_files_response.status_code == 200

    audio_files = audio_files_response.json()
    assert len(audio_files) > 0

    file_name = "preprocessed_sample.wav"
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/{file_name}")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "audio/wav"

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/nonexistent.wav")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Test with potentially malicious file name
    malicious_filename = urllib.parse.quote("../../../../etc/passwd")
    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/{malicious_filename}")
    assert response.status_code != 200


def test_get_transcription(preprocessed_client: TestClient) -> None:
    """Test retrieving SRT transcription for a pre-populated episode."""
    episode_id = _get_episode_id(preprocessed_client)

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/srt")
    assert response.status_code == status.HTTP_200_OK

    srt_content = response.text
    assert isinstance(srt_content, str)
    assert len(srt_content) > 0

    assert "This is a sample transcript." in srt_content
    assert "For testing purposes only." in srt_content

    assert "00:00:00,000 --> 00:00:05,000" in srt_content
    assert "00:00:05,500 --> 00:00:10,000" in srt_content


def test_preprocessed_resources_with_invalid_episode_prepopulated(preprocessed_client: TestClient) -> None:
    """Test retrieving preprocessed resources with an invalid episode ID."""
    invalid_id = "nonexistent-id"

    response = preprocessed_client.get(f"/v1/episodes/{invalid_id}/audios")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = preprocessed_client.get(f"/v1/episodes/{invalid_id}/audio/file.wav")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = preprocessed_client.get(f"/v1/episodes/{invalid_id}/srt")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_preprocessed_resources_before_preprocessing_prepopulated(session: Session, preprocessed_client: TestClient) -> None:
    """Test retrieving preprocessed resources for an episode before preprocessing is complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audios")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/audio/file.wav")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = preprocessed_client.get(f"/v1/episodes/{episode_id}/srt")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


#####################################
# MARK: Audio editing endpoints tests
#####################################


def test_get_edited_combined_audio(edited_client: TestClient) -> None:
    """Test retrieving edited combined audio for a pre-populated episode."""
    episode_id = _get_episode_id(edited_client)

    response = edited_client.get(f"/v1/episodes/{episode_id}/edited-audio")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0


def test_apply_audio_edits_invalid_episode(edited_client: TestClient) -> None:
    """Test applying audio edits to a non-existent episode."""
    response = edited_client.post("/v1/episodes/nonexistent-id/audio-edits")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"


def test_apply_audio_edits_preprocessing_incomplete(session: Session, edited_client: TestClient) -> None:
    """Test applying audio edits when preprocessing is not complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = edited_client.post(f"/v1/episodes/{episode_id}/audio-edits")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = edited_client.get(f"/v1/episodes/{episode_id}/edited-audio")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_edited_audio_not_found(edited_client: TestClient) -> None:
    """Test getting edited audio for a non-existent episode."""
    response = edited_client.get("/v1/episodes/nonexistent-id/edited-audio")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"


#####################################
# MARK: Postprocessing tests
#####################################


def test_get_postprocessed_audio(postprocessed_client: TestClient) -> None:
    """Test retrieving postprocessed audio for a pre-populated episode."""
    episode_id = _get_episode_id(postprocessed_client)

    response = postprocessed_client.get(f"/v1/episodes/{episode_id}/postprocessed-audio")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0


def test_postprocess_invalid_episode(postprocessed_client: TestClient) -> None:
    """Test initiating postprocessing for a non-existent episode."""
    response = postprocessed_client.post("/v1/episodes/nonexistent-id/postprocess")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"

    response = postprocessed_client.get("/v1/episodes/nonexistent-id/postprocessed-audio")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"


def test_postprocess_preprocessing_incomplete(session: Session, postprocessed_client: TestClient) -> None:
    """Test initiating postprocessing when preprocessing is not complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = postprocessed_client.post(f"/v1/episodes/{episode_id}/postprocess")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = postprocessed_client.get(f"/v1/episodes/{episode_id}/postprocessed-audio")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


#####################################
# MARK: Transcription Management tests
#####################################


def test_get_and_update_annotated_srt(postprocessed_client: TestClient) -> None:
    """Test retrieving annotated SRT for a postprocessed episode."""
    episode_id = _get_episode_id(postprocessed_client)

    response = postprocessed_client.get(f"/v1/episodes/{episode_id}/annotated-srt")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "content" in data
    assert isinstance(data["content"], str)
    assert len(data["content"]) > 0

    assert "This is a postprocessed transcript." in data["content"]
    assert "For testing purposes only." in data["content"]

    updated_content = "UPDATED"
    update_response = postprocessed_client.put(f"/v1/episodes/{episode_id}/annotated-srt", json={"content": updated_content})
    assert update_response.status_code == 200

    get_response_after = postprocessed_client.get(f"/v1/episodes/{episode_id}/annotated-srt")
    assert get_response_after.status_code == 200
    after_content = get_response_after.json()["content"]
    assert after_content == updated_content


def test_transcription_management_invalid_episode(postprocessed_client: TestClient) -> None:
    """Test transcription management endpoints with non-existent episode."""
    response = postprocessed_client.get("/v1/episodes/nonexistent-id/annotated-srt")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = postprocessed_client.put("/v1/episodes/nonexistent-id/annotated-srt", json={"content": "Test content"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_transcription_management_preprocessing_incomplete(session: Session, postprocessed_client: TestClient) -> None:
    """Test transcription management endpoints when postprocessing is not complete."""
    episode = Episode(title="Test Episode", preprocess_status=JobStatus.completed, postprocess_status=JobStatus.pending)
    session.add(episode)
    session.commit()

    episode_id = episode.uuid

    response = postprocessed_client.get(f"/v1/episodes/{episode_id}/annotated-srt")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = postprocessed_client.put(f"/v1/episodes/{episode_id}/annotated-srt", json={"content": "Test content"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


#####################################
# MARK: Metadata Generation Tests
#####################################


def test_get_chapter_info(metadata_client: TestClient) -> None:
    """Test retrieving chapter information."""
    episode_id = _get_episode_id(metadata_client)

    response = metadata_client.get(f"/v1/episodes/{episode_id}/metadata-audio")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "audio/wav"
    assert len(response.content) > 0

    response = metadata_client.get(f"/v1/episodes/{episode_id}/chapters")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.text) > 0

    response = metadata_client.get(f"/v1/episodes/{episode_id}/show-notes")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.text) > 0


def test_get_metadata_errors(metadata_client: TestClient, session: Session) -> None:
    """Test error responses for getting metadata."""
    response = metadata_client.get("/v1/episodes/nonexistent-id/chapters")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = metadata_client.get("/v1/episodes/nonexistent-id/show-notes")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    episode = Episode(
        title="Incomplete Metadata", preprocess_status=JobStatus.completed, postprocess_status=JobStatus.completed, metadata_generation_status=JobStatus.pending
    )
    session.add(episode)
    session.commit()

    response = metadata_client.get(f"/v1/episodes/{episode.uuid}/chapters")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = metadata_client.get(f"/v1/episodes/{episode.uuid}/show-notes")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_missing_files(metadata_client: TestClient, monkeypatch: MonkeyPatch) -> None:
    """Test responses when files are missing."""
    episode_id = _get_episode_id(metadata_client)

    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        monkeypatch.setattr("app.v1.router.app_dir", temp_dir_path)

        episode_dir = temp_dir_path / "episodes" / episode_id
        metadata_dir = episode_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        response = metadata_client.get(f"/v1/episodes/{episode_id}/chapters")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Chapter file not found" in response.json()["detail"]

        response = metadata_client.get(f"/v1/episodes/{episode_id}/show-notes")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Show notes file not found" in response.json()["detail"]


#####################################
# MARK: Export endpoints
#####################################


def test_download_export(export_client: TestClient) -> None:
    """Test downloading an exported zip file."""
    episode_id = _get_episode_id(export_client)

    response = export_client.get(f"/v1/episodes/{episode_id}/export")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/zip"
    assert "content-disposition" in response.headers


def test_download_export_not_found(export_client: TestClient) -> None:
    """Test downloading an export for a non-existent episode."""
    response = export_client.get("/v1/episodes/nonexistent-id/export")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Episode not found"


def test_download_export_not_completed(session: Session, export_client: TestClient) -> None:
    """Test downloading an export before the export is completed."""
    episode = Episode(
        title="Pending Export",
        preprocess_status=JobStatus.completed,
        edit_status=JobStatus.completed,
        postprocess_status=JobStatus.completed,
        metadata_generation_status=JobStatus.completed,
        export_status=JobStatus.pending,
    )
    session.add(episode)
    session.commit()

    response = export_client.get(f"/v1/episodes/{episode.uuid}/export")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


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
        assert response.status_code == status.HTTP_201_CREATED

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
        assert response.status_code == status.HTTP_200_OK

        edited_audio_files = list((episode_dir / "edited").glob("*.wav"))
        assert len(edited_audio_files) == (len(wav_files) - 1)

        edited_combined_file = episode_dir / "edited-combined.wav"
        assert edited_combined_file.exists()
        assert edited_combined_file.stat().st_size > 0

        response = client.get(f"/v1/episodes/{data['uuid']}/edited-audio")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "audio/wav"
        assert len(response.content) > 0

        # Postprocess
        response = client.post(f"/v1/episodes/{data['uuid']}/postprocess")
        assert response.status_code == status.HTTP_202_ACCEPTED

        postprocessed_audio_files = list((episode_dir / "postprocessed").glob("*.wav"))
        assert len(postprocessed_audio_files) > 0
        assert postprocessed_audio_files[0].stat().st_size > 0

        postprocessed_srt_files = list((episode_dir / "postprocessed").glob("*.srt"))
        assert len(postprocessed_srt_files) > 0

        response = client.get(f"/v1/episodes/{data['uuid']}/postprocessed-audio")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "audio/wav"
        assert len(response.content) > 0

        response = client.get(f"/v1/episodes/{data['uuid']}/annotated-srt")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.content) > 0

        annotated_srt_content = (
            "1\n00:00:00.000 --> 00:00:01.540\nkotaro: なんかジャンプできるようになってる\n\n# Test1\n\n"
            "2\n00:00:02.250 --> 00:00:03.250\nshun: ありがとうございました\n\n# Test2 \n\n- [testurl](https://www.youtube.com/watch?v=1)\n\n"
            "3\n00:00:03.250 --> 00:00:07.750\nmasa: マークダウンの目次みたいなのが右に出てくるっていうイメージでやってました\n\n"
        )
        response = client.put(f"/v1/episodes/{data['uuid']}/annotated-srt", json={"content": annotated_srt_content})
        assert response.status_code == status.HTTP_200_OK

        # Metadata generation
        response = client.post(f"/v1/episodes/{data['uuid']}/metadata")
        assert response.status_code == status.HTTP_202_ACCEPTED

        response = client.get(f"/v1/episodes/{data['uuid']}/chapters")
        assert response.status_code == status.HTTP_200_OK
        content = response.content.decode("utf-8")
        assert "- (00:02) Test1" in content
        assert "- (00:03) Test2" in content

        response = client.get(f"/v1/episodes/{data['uuid']}/show-notes")
        assert response.status_code == status.HTTP_200_OK
        content = response.content.decode("utf-8")
        assert "- [testurl](https://www.youtube.com/watch?v=1)" in content

        # Export
        response = client.post(f"/v1/episodes/{data['uuid']}/export")
        assert response.status_code == status.HTTP_202_ACCEPTED

        response = client.get(f"/v1/episodes/{data['uuid']}/export")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/zip"
