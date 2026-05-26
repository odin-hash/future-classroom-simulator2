import os
import hashlib
import asyncio
import edge_tts
from typing import Dict, Any

# Resolve absolute paths relative to the backend directory
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BACKEND_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Map student names to their voice profiles
# Edge TTS voices: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support
# Using Indian English voices + pitch/rate adjustments to sound like school children
STUDENT_VOICE_MAP = {
    # Primary student names from simulation
    "aarav": {
        "voice": "en-IN-PrabhatNeural",       # Indian English male
        "rate": "+8%",                          # Slightly fast, enthusiastic
        "pitch": "+25%",                        # Higher pitch for young boy
        "personality": "curious"
    },
    "ananya": {
        "voice": "en-IN-NeerjaExpressiveNeural",  # Indian English female, expressive
        "rate": "-10%",                            # Slower, shy/hesitant
        "pitch": "+30%",                           # High pitch, young girl
        "personality": "shy"
    },
    "vihaan": {
        "voice": "en-IN-PrabhatNeural",        # Indian English male
        "rate": "-5%",                          # Slightly slow, lazy/distracted
        "pitch": "+20%",                        # Young boy pitch
        "personality": "distracted"
    },
    "ishaan": {
        "voice": "en-IN-PrabhatNeural",        # Indian English male
        "rate": "+18%",                         # Fast, hyperactive
        "pitch": "+35%",                        # Highest pitch, excited kid
        "personality": "hyperactive"
    },
    "riya": {
        "voice": "en-IN-NeerjaExpressiveNeural",  # Indian English female
        "rate": "-12%",                            # Slow, struggling
        "pitch": "+28%",                           # Young girl pitch
        "personality": "weak_learner"
    },
    "kabir": {
        "voice": "en-IN-PrabhatNeural",        # Indian English male
        "rate": "+10%",                         # Quick, confident
        "pitch": "+18%",                        # Medium-high, cocky boy
        "personality": "overconfident"
    },
}

# Hindi voice mappings (for Hindi language sessions)
HINDI_VOICES = {
    "male": "hi-IN-MadhurNeural",
    "female": "hi-IN-SwaraNeural",
}

# Bengali voice mappings (for Bengali language sessions)
BENGALI_VOICES = {
    "male": "bn-IN-BashkarNeural",
    "female": "bn-IN-TanishaaNeural",
}

# Gender map for language-specific voice selection
STUDENT_GENDER = {
    "aarav": "male",
    "ananya": "female",
    "vihaan": "male",
    "ishaan": "male",
    "riya": "female",
    "kabir": "male",
}


def _get_voice_config(student_name: str, language: str = "English") -> Dict[str, str]:
    """
    Returns the voice ID and prosody settings for a student.
    Selects language-appropriate voice while keeping personality-based rate/pitch.
    """
    name_key = student_name.lower().strip()
    config = STUDENT_VOICE_MAP.get(name_key, STUDENT_VOICE_MAP["aarav"])
    gender = STUDENT_GENDER.get(name_key, "male")

    # Override voice ID for non-English languages
    lang_lower = language.lower() if language else "english"
    if "hindi" in lang_lower:
        voice = HINDI_VOICES[gender]
    elif "bengali" in lang_lower or "bangla" in lang_lower:
        voice = BENGALI_VOICES[gender]
    else:
        voice = config["voice"]

    return {
        "voice": voice,
        "rate": config["rate"],
        "pitch": config["pitch"],
    }


def _detect_script(text: str) -> str:
    """
    Auto-detect the script of the text by checking Unicode character ranges.
    Returns 'hindi', 'bengali', or 'english'.
    """
    devanagari_count = 0
    bengali_count = 0
    latin_count = 0

    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:  # Devanagari block
            devanagari_count += 1
        elif 0x0980 <= cp <= 0x09FF:  # Bengali block
            bengali_count += 1
        elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):  # Latin A-Z/a-z
            latin_count += 1

    # If there's ANY non-Latin script, use that language
    # (English voices can't pronounce Hindi/Bengali at all, so even 1 character matters)
    if devanagari_count > 0 and devanagari_count >= bengali_count:
        return "hindi"
    elif bengali_count > 0 and bengali_count > devanagari_count:
        return "bengali"
    return "english"


# In-memory TTS Cache to eliminate any file read/write latency and disk dependency
TTS_CACHE: Dict[str, bytes] = {}


async def generate_speech_audio(text: str, student_name: str, language: str = "English") -> bytes:
    """
    Main TTS synthesis function.
    Uses Microsoft Edge Neural TTS for natural, human-like voices.
    Checks the in-memory cache first, then generates new audio bytes asynchronously.
    Returns raw MP3 audio bytes.
    """
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Cannot synthesize speech for an empty text string.")

    # Auto-detect script from the actual text content as a safety net
    # This ensures Hindi/Bengali text ALWAYS uses the correct voice
    detected_script = _detect_script(clean_text)
    if detected_script == "hindi":
        language = "Hindi"
    elif detected_script == "bengali":
        language = "Bengali"

    # Get voice configuration for this student + language
    config = _get_voice_config(student_name, language)
    voice = config["voice"]
    rate = config["rate"]
    pitch = config["pitch"]

    # Generate cache key based on voice + prosody + text
    hash_payload = f"{voice}_{rate}_{pitch}_{clean_text}"
    text_hash = hashlib.md5(hash_payload.encode("utf-8")).hexdigest()

    # In-memory Cache hit — return bytes immediately
    if text_hash in TTS_CACHE:
        print(f"[Edge TTS] In-memory cache hit for '{clean_text[:30]}...'")
        return TTS_CACHE[text_hash]

    # Cache miss — synthesize with Edge TTS asynchronously
    try:
        print(f"[Edge TTS] Synthesizing asynchronously for {student_name} ({voice}, rate={rate}, pitch={pitch}) -> '{clean_text[:50]}...'")

        communicate = edge_tts.Communicate(
            text=clean_text,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )

        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])

        audio_bytes = bytes(audio_data)
        if not audio_bytes:
            raise ValueError("Synthesized audio data is empty.")

        # Cache the bytes in memory
        TTS_CACHE[text_hash] = audio_bytes
        print(f"[Edge TTS] Successfully generated in-memory bytes ({len(audio_bytes)} bytes)")
        return audio_bytes

    except Exception as e:
        print(f"[Edge TTS Error] Async synthesis failed: {e}")
        raise e
