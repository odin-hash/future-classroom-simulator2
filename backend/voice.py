import os
import hashlib
import asyncio
import time
import edge_tts
from collections import OrderedDict
from typing import Dict, Any


# Purely in-memory audio caching is utilized to support read-only production filesystems.

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


class TTLCache:
    """
    A memory-safe, zero-dependency in-memory cache system combining 
    Time-To-Live (TTL) expiration and Least-Recently-Used (LRU) eviction boundaries.
    """
    def __init__(self, maxsize: int = 500, ttl: float = 1800.0):
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache = OrderedDict()  # key -> (value, expiry_timestamp)

    def get(self, key: str):
        if key not in self.cache:
            return None
        value, expiry = self.cache[key]
        if time.time() > expiry:
            del self.cache[key]  # Auto-expire
            return None
        # Move key to end to maintain LRU access order
        self.cache.move_to_end(key)
        return value

    def set(self, key: str, value: any):
        now = time.time()
        self.cleanup()
        if key in self.cache:
            del self.cache[key]
        elif len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)  # Evict oldest entry (LRU/FIFO)
        self.cache[key] = (value, now + self.ttl)

    def cleanup(self):
        """Scans and evicts expired records from memory."""
        now = time.time()
        expired = [k for k, (_, exp) in self.cache.items() if now > exp]
        for k in expired:
            del self.cache[k]


# Instantiate memory-safe controlled TTS Cache (max 500 MP3 audio entries, 30 min duration)
TTS_CACHE = TTLCache(maxsize=500, ttl=1800.0)

# Global map of asyncio.Locks to prevent cache stampedes
_pending_tts_locks: Dict[str, asyncio.Lock] = {}


async def generate_speech_audio(text: str, student_name: str, language: str = "English") -> tuple[bytes, bool]:
    """
    Main TTS synthesis function.
    Uses Microsoft Edge Neural TTS for natural, human-like voices.
    Checks the memory-safe in-memory cache first, then generates new audio bytes asynchronously.
    Uses asyncio.Locks dynamically per text hash to prevent concurrent request stampedes.
    Wraps synthesis in a 3-attempt exponential backoff retry system for maximum network resilience.
    Returns raw MP3 audio bytes and a boolean representing whether it was a cache hit.
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
    cached_val = TTS_CACHE.get(text_hash)
    if cached_val is not None:
        print(f"[Edge TTS] In-memory cache hit for '{clean_text[:30]}...'")
        return cached_val, True

    # Ensure a single lock exists for this cache key to block concurrent redundant synthesis
    if text_hash not in _pending_tts_locks:
        _pending_tts_locks[text_hash] = asyncio.Lock()

    async with _pending_tts_locks[text_hash]:
        # Double check cache within lock boundary to consume newly synthesized results
        cached_val = TTS_CACHE.get(text_hash)
        if cached_val is not None:
            print(f"[Edge TTS] Stampede avoided! Consumed cached bytes for key '{text_hash}'")
            return cached_val, True

        # Cache miss — synthesize with Edge TTS asynchronously with resilient retry
        max_retries = 3
        base_delay = 0.5
        
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[Edge TTS] Synthesizing for {student_name} (attempt {attempt}/{max_retries}) -> '{clean_text[:50]}...'")

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
                TTS_CACHE.set(text_hash, audio_bytes)
                print(f"[Edge TTS] Successfully generated bytes in attempt {attempt} ({len(audio_bytes)} bytes)")
                return audio_bytes, False

            except Exception as e:
                print(f"[Edge TTS Warning] Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    print("[Edge TTS Error] All retry attempts exhausted. Raising exception.")
                    raise e
                
                # Exponential backoff: 0.5s -> 1.0s -> 2.0s
                delay = base_delay * (2 ** (attempt - 1))
                print(f"[Edge TTS] Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

