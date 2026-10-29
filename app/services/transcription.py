from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openai import OpenAI

from ..config import get_settings


def _load_audio(audio_path: str) -> tuple[str, bytes]:
    settings = get_settings()
    if audio_path.startswith("gs://"):
        from google.cloud import storage

        bucket_name, object_name = audio_path[5:].split("/", 1)
        content = (
            storage.Client(project=settings.google_cloud_project or None)
            .bucket(bucket_name)
            .blob(object_name)
            .download_as_bytes()
        )
        return Path(object_name).name, content
    path = Path(audio_path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Stored audio file does not exist")
    return path.name, path.read_bytes()


def transcribe_recorded_audio(audio_path: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for file transcription")
    filename, content = _load_audio(audio_path)
    file_object = BytesIO(content)
    file_object.name = filename
    result = OpenAI(api_key=settings.openai_api_key).audio.transcriptions.create(
        model=settings.openai_file_transcribe_model,
        file=file_object,
        prompt="한국어 수학 문제 풀이 think-aloud 녹음",
        keywords=["원탁", "이항정리", "조합", "실수", "허수", "전이행렬"],
        languages=["ko"],
        response_format="json",
    )
    text = getattr(result, "text", None)
    if not text and isinstance(result, str):
        text = result
    if not text:
        raise RuntimeError("File transcription returned no text")
    return text.strip()

