"""Voice output (gTTS, ElevenLabs), voice cloning and speech-to-text (Groq Whisper)."""

import io
import os
import re

import groq
from elevenlabs.client import ElevenLabs
from groq import Groq
from gtts import gTTS

DEFAULT_VOICE_ID = "XrExE9yKIg1WjnnlVkGX"  # Matilda (premade; free plans can use premade voices)
EL_MODEL = "eleven_multilingual_v2"
# eleven_multilingual_v2 does not support these languages (checked via
# the ElevenLabs models API); eleven_flash_v2_5 does
EL_FALLBACK_MODEL = "eleven_flash_v2_5"
EL_FALLBACK_LANGUAGES = {"vi"}
DEFAULT_WHISPER_MODEL = "whisper-large-v3"

AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}


def clean_for_speech(text: str) -> str:
    """Remove markdown symbols and emojis so they are not read aloud."""
    text = re.sub(r"[*_#`>|~]", "", text)
    text = re.sub(
        "[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]", "", text
    )
    return re.sub(r"\s+", " ", text).strip()


def speak_gtts(
    text: str,
    lang_code: str
) -> bytes:
    """Free text-to-speech. Returns MP3 bytes, or None if it fails."""
    try:
        tts = gTTS(
            text=clean_for_speech(text),
            lang=lang_code,
            slow=False
        )
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        return audio_buffer.getvalue()
    except Exception as e:
        print(f"gTTS error: {e}")
        return None


def list_voices(api_key: str) -> dict:
    """Voices this ElevenLabs account can use: {name: voice_id}.

    Free plans can use premade voices and their own clones, not library voices.
    """
    try:
        client = ElevenLabs(api_key=api_key)
        voices = client.voices.search(page_size=100).voices
        return {
            v.name: v.voice_id for v in voices
            if v.category in ("premade", "cloned", "generated", "professional")
        }
    except Exception as e:
        print(f"ElevenLabs voice list error: {e}")
        return {}


def get_plan(api_key: str) -> dict:
    """ElevenLabs plan name and whether it allows instant voice cloning."""
    try:
        sub = ElevenLabs(api_key=api_key).user.subscription.get()
        return {
            "tier": sub.tier,
            "can_clone": bool(getattr(sub, "can_use_instant_voice_cloning", False)),
        }
    except Exception as e:
        print(f"ElevenLabs plan check error: {e}")
        return {"tier": "unknown", "can_clone": False}


def speak_elevenlabs(
    text: str,
    api_key: str,
    voice_id: str = DEFAULT_VOICE_ID,
    lang_code: str = None
) -> bytes:
    """Premium text-to-speech. Returns MP3 bytes, or None if it fails."""
    try:
        client = ElevenLabs(
            api_key=api_key
        )
        audio = (
            client.text_to_speech
            .convert(
                voice_id=voice_id,
                text=clean_for_speech(text),
                model_id=(
                    EL_FALLBACK_MODEL if lang_code in EL_FALLBACK_LANGUAGES
                    else EL_MODEL
                )
            )
        )
        return b"".join(audio)
    except Exception as e:
        print(
            f"ElevenLabs error: {e}"
        )
        return None


def clone_voice(
    api_key: str,
    name: str,
    audio_bytes: bytes,
    filename: str = "sample.mp3"
) -> str:
    """Create an instant voice clone. Returns the new voice_id, or None.

    Sends the audio itself as (filename, bytes, mime type): the SDK treats
    a plain string as file contents, not as a path.
    Needs a paid ElevenLabs plan (Starter or above).
    """
    ext = os.path.splitext(filename)[1].lower()
    try:
        client = ElevenLabs(
            api_key=api_key
        )
        voice = client.voices.ivc.create(
            name=name,
            files=[(filename, audio_bytes, AUDIO_MIME.get(ext, "audio/mpeg"))]
        )
        return voice.voice_id
    except Exception as e:
        print(
            f"Voice clone error: {e}"
        )
        return None


def transcribe_audio_file(
    audio_bytes: bytes,
    api_key: str,
    language: str = None,
    filename: str = "question.wav"
) -> str:
    """Speech to text with Groq Whisper. Returns "" if it fails.

    language: optional ISO-639-1 hint (e.g. "hi"), improves accuracy.
    """
    client = Groq(api_key=api_key)
    try:
        result = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=os.getenv("GROQ_WHISPER_MODEL") or DEFAULT_WHISPER_MODEL,
            language=language or groq.NOT_GIVEN,
            response_format="text"
        )
        # response_format="text" returns a plain string
        return (result if isinstance(result, str) else getattr(result, "text", "")).strip()
    except Exception as e:
        print(
            f"Transcription error: {e}"
        )
        return ""
