"""Voice output (gTTS, ElevenLabs), voice cloning and speech-to-text (Groq Whisper)."""

import io
import os
import re
import time

import groq
from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings
from groq import Groq
from gtts import gTTS

# Voice speed choices. The free Google voice only has normal and slow;
# ElevenLabs supports a real speed setting (about 0.7 to 1.2).
SPEEDS = ["Slow", "Normal", "Fast"]
EL_SPEED = {"Slow": 0.8, "Normal": 1.0, "Fast": 1.15}

DEFAULT_VOICE_ID = "XrExE9yKIg1WjnnlVkGX"  # Matilda (premade; free plans can use premade voices)
EL_MODEL = "eleven_multilingual_v2"
# eleven_multilingual_v2 does not support these languages (checked via
# the ElevenLabs models API); eleven_flash_v2_5 does
EL_FALLBACK_MODEL = "eleven_flash_v2_5"
EL_FALLBACK_LANGUAGES = {"vi"}
DEFAULT_WHISPER_MODEL = "whisper-large-v3"

# Every voice cloned through iRaaya carries this label, so the automatic
# cleanup only ever touches iRaaya clones, never voices made elsewhere
CLONE_LABEL = {"source": "iraaya"}
CLONE_MAX_AGE_DAYS = 7

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
    lang_code: str,
    speed: str = "Normal"
) -> bytes:
    """Free text-to-speech. Returns MP3 bytes, or None if it fails.
    Only "Slow" changes the speed; Google's free voice has no fast mode."""
    try:
        tts = gTTS(
            text=clean_for_speech(text),
            lang=lang_code,
            slow=(speed == "Slow")
        )
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        return audio_buffer.getvalue()
    except Exception as e:
        print(f"gTTS error: {e}")
        return None


def list_voices(api_key: str) -> dict:
    """Standard (premade) voices everyone may use: {name: voice_id}.

    Cloned voices are deliberately left out: a clone belongs to the person
    who made it and is only offered in their own session (see app.py).
    """
    try:
        client = ElevenLabs(api_key=api_key)
        voices = client.voices.search(page_size=100).voices
        return {
            v.name: v.voice_id for v in voices
            if v.category == "premade"
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
    lang_code: str = None,
    speed: str = "Normal"
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
                ),
                voice_settings=(
                    VoiceSettings(speed=EL_SPEED[speed]) if speed in EL_SPEED
                    and speed != "Normal" else None
                ),
            )
        )
        return b"".join(audio)
    except Exception as e:
        print(
            f"ElevenLabs error: {e}"
        )
        return None


class VoiceCloneError(Exception):
    """Voice cloning failed; the message says why, in plain words."""


def clone_voice(
    api_key: str,
    name: str,
    audio_bytes: bytes,
    filename: str = "sample.mp3"
) -> str:
    """Create an instant voice clone. Returns the new voice_id.

    Raises VoiceCloneError with ElevenLabs' reason if it fails.

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
            files=[(filename, audio_bytes, AUDIO_MIME.get(ext, "audio/mpeg"))],
            # A plain dict: the API rejects a JSON string here
            labels=CLONE_LABEL,
            description="Created by iRaaya. Private to the person who made it.",
        )
        return voice.voice_id
    except Exception as e:
        print(
            f"Voice clone error: {e}"
        )
        body = getattr(e, "body", None)
        detail = body.get("detail") if isinstance(body, dict) else None
        reason = (
            detail.get("message") if isinstance(detail, dict) else detail
        ) or str(e)[:200]
        raise VoiceCloneError(reason) from e


def delete_voice(api_key: str, voice_id: str) -> bool:
    """Permanently delete a cloned voice from ElevenLabs."""
    try:
        ElevenLabs(api_key=api_key).voices.delete(voice_id=voice_id)
        return True
    except Exception as e:
        print(f"Voice delete error: {e}")
        return False


def is_expired_iraaya_clone(voice, now: float = None) -> bool:
    """True for an iRaaya-made clone older than CLONE_MAX_AGE_DAYS."""
    now = now or time.time()
    labels = voice.labels or {}
    created = voice.created_at_unix
    return (
        voice.category == "cloned"
        and labels.get("source") == CLONE_LABEL["source"]
        and created is not None
        and now - created > CLONE_MAX_AGE_DAYS * 86400
    )


def cleanup_old_clones(api_key: str) -> int:
    """Delete iRaaya clones older than 7 days. Returns how many were deleted."""
    try:
        client = ElevenLabs(api_key=api_key)
        voices = client.voices.search(page_size=100, category="cloned").voices
    except Exception as e:
        print(f"Clone cleanup error: {e}")
        return 0
    deleted = 0
    for v in voices:
        if is_expired_iraaya_clone(v) and delete_voice(api_key, v.voice_id):
            deleted += 1
    return deleted


# Whisper is known to "hear" these phrases in silence or background noise
WHISPER_FILLERS = {
    "", "you", "thank you", "thanks", "thank you very much", "thanks for watching",
    "thank you for watching", "bye", "bye bye", "okay", "ok", "so", "hmm",
    "please subscribe", "subtitles by the amara org community",
}


def is_filler(text: str) -> bool:
    """True if a transcript is empty or a typical Whisper phantom phrase."""
    t = re.sub(r"[^a-z ]", "", (text or "").lower()).strip()
    return t in WHISPER_FILLERS


def transcribe_audio_file(
    audio_bytes: bytes,
    api_key: str,
    language: str = None,
    filename: str = "question.wav",
    vocabulary: str = None
) -> str:
    """Speech to text with Groq Whisper. Returns "" if it fails.

    language: optional ISO-639-1 hint (e.g. "hi"), improves accuracy.
    vocabulary: names from the user's data, so Whisper spells them right
    (e.g. "Nexthink" rather than "next thing").
    """
    client = Groq(api_key=api_key)
    try:
        result = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=os.getenv("GROQ_WHISPER_MODEL") or DEFAULT_WHISPER_MODEL,
            language=language or groq.NOT_GIVEN,
            prompt=(
                f"Names that may be mentioned: {vocabulary}." if vocabulary
                else groq.NOT_GIVEN
            ),
            response_format="text"
        )
        # response_format="text" returns a plain string
        text = (result if isinstance(result, str) else getattr(result, "text", "")).strip()
        return "" if is_filler(text) else text
    except Exception as e:
        print(
            f"Transcription error: {e}"
        )
        return ""
