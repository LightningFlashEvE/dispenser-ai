import asyncio
import base64
import io
import logging
import struct
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TranscribeResult:
    text: str
    segments: list[dict[str, Any]]
    language: str
    duration_ms: int
    error: str | None = None


@dataclass
class VadSegment:
    start_ms: int
    end_ms: int
    duration_ms: int


class WhisperServerClient:
    def __init__(self, base_url: str = None, timeout: float = 30.0):
        self.base_url = base_url or settings.whisper_server_url
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            transport = httpx.AsyncHTTPTransport(proxy=None)
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=transport,
                trust_env=False,
            )
        return self._client

    async def health(self) -> dict:
        client = await self._get_client()
        try:
            resp = await client.get("/")
            return {"status": "ok", "code": resp.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def transcribe_pcm(
        self,
        pcm_data: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        bits_per_sample: int = 16,
    ) -> TranscribeResult:
        wav_data = self._pcm_to_wav(pcm_data, sample_rate, channels, bits_per_sample)
        return await self.transcribe_wav(wav_data)

    async def transcribe_wav(self, wav_data: bytes) -> TranscribeResult:
        client = await self._get_client()
        try:
            files = {"file": ("audio.wav", wav_data, "audio/wav")}
            resp = await client.post("/inference", files=files)
            resp.raise_for_status()
            body = resp.json()
            return self._parse_response(body)
        except httpx.TimeoutException:
            logger.error("whisper-server 转写超时")
            return TranscribeResult(
                text="",
                segments=[],
                language="",
                duration_ms=0,
                error="转写超时",
            )
        except httpx.HTTPStatusError as e:
            logger.error("whisper-server HTTP 错误: %d", e.response.status_code)
            return TranscribeResult(
                text="",
                segments=[],
                language="",
                duration_ms=0,
                error=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            logger.exception("whisper-server 转写异常")
            return TranscribeResult(
                text="",
                segments=[],
                language="",
                duration_ms=0,
                error=str(e),
            )

    async def transcribe_base64(
        self,
        base64_pcm: str,
        sample_rate: int = 16000,
    ) -> TranscribeResult:
        pcm_data = base64.b64decode(base64_pcm)
        return await self.transcribe_pcm(pcm_data, sample_rate)

    async def transcribe_chunks(
        self,
        chunks: list[bytes],
        sample_rate: int = 16000,
    ) -> TranscribeResult:
        combined_pcm = b"".join(chunks)
        return await self.transcribe_pcm(combined_pcm, sample_rate)

    def _pcm_to_wav(
        self,
        pcm_data: bytes,
        sample_rate: int,
        channels: int,
        bits_per_sample: int,
    ) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(bits_per_sample // 8)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()

    def _parse_response(self, body: dict) -> TranscribeResult:
        text = body.get("text", "")
        segments = body.get("segments", [])
        language = body.get("language", "zh")
        duration_ms = 0
        if segments:
            last_seg = segments[-1]
            end_ts = last_seg.get("end", 0)
            duration_ms = int(end_ts * 1000)
        return TranscribeResult(
            text=text.strip(),
            segments=segments,
            language=language,
            duration_ms=duration_ms,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class AudioSession:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.chunks: list[bytes] = []
        self.start_time: datetime = datetime.now(timezone.utc)
        self.total_bytes: int = 0
        self.is_recording: bool = False

    def add_chunk(self, chunk: bytes) -> None:
        self.chunks.append(chunk)
        self.total_bytes += len(chunk)

    def add_base64_chunk(self, base64_data: str) -> None:
        chunk = base64.b64decode(base64_data, validate=True)
        self.add_chunk(chunk)

    def get_combined_pcm(self) -> bytes:
        return b"".join(self.chunks)

    def get_duration_ms(self) -> int:
        bytes_per_ms = self.sample_rate * 2 // 1000
        return self.total_bytes // bytes_per_ms if bytes_per_ms > 0 else 0

    def reset(self) -> None:
        self.chunks = []
        self.start_time = datetime.now(timezone.utc)
        self.total_bytes = 0
        self.is_recording = False

    def start_recording(self) -> None:
        self.reset()
        self.is_recording = True

    def stop_recording(self) -> None:
        self.is_recording = False


_whisper_client: WhisperServerClient | None = None
_client_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


async def get_whisper_client_async() -> WhisperServerClient:
    global _whisper_client
    if _whisper_client is not None:
        return _whisper_client
    async with _get_lock():
        if _whisper_client is None:
            _whisper_client = WhisperServerClient()
    return _whisper_client


def get_whisper_client() -> WhisperServerClient:
    global _whisper_client
    if _whisper_client is None:
        _whisper_client = WhisperServerClient()
    return _whisper_client
