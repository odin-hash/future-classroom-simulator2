"""
AI Intelligence Engine for Future Classroom Simulator.

This module handles:
- Personality-driven student response generation via LLM cascade
- Provider chain: Gemini 2.0 Flash → Groq (Llama 3.3) → Ollama (local) → Templates
- Structured memory management per student
- Evidence-based teacher evaluation
- Personality-aware fallback templates

Supported providers (set via environment variables):
  GEMINI_API_KEY    → Google Gemini 2.0 Flash
  GROQ_API_KEY      → Groq Cloud (Llama 3.3 70B)
  OLLAMA_BASE_URL   → Ollama local server (default: http://localhost:11434)
"""

import os
import json
import random
import re
import httpx
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session as DBSession
from models import StudentState
from personality import (
    STUDENT_PERSONALITIES,
    get_student_memory,
    update_student_memory,
    format_memory_for_prompt,
    get_grade_key,
)


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER CLIENTS
# ──────────────────────────────────────────────────────────────────────────────

def _get_gemini_client():
    """Returns a configured Gemini client, or None if no API key is set."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai as google_genai
        return google_genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[Gemini] Client init error: {e}")
        return None


def _has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


async def _call_gemini(prompt: str) -> Optional[str]:
    """Call Gemini 2.0 Flash. Returns response text or None on failure."""
    client = _get_gemini_client()
    if not client:
        return None
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text
        if text:
            print(f"[Gemini] ✓ Response received ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[Gemini] ✗ Error: {e}")
        return None


async def _call_groq(prompt: str) -> Optional[str]:
    """Call Groq API (Llama 3.3 70B). Returns response text or None on failure."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 300,
                },
                timeout=20.0,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                print(f"[Groq] ✓ Response received ({len(text)} chars)")
                return text
            else:
                print(f"[Groq] ✗ HTTP {resp.status_code}: {resp.text[:200]}")
                return None
    except Exception as e:
        print(f"[Groq] ✗ Error: {e}")
        return None


async def _call_ollama(prompt: str) -> Optional[str]:
    """Call Ollama local server. Returns response text or None on failure."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    # Try common model names in order of preference
    models = os.environ.get("OLLAMA_MODEL", "llama3.2,llama3.1,gemma2,mistral").split(",")

    for model_name in models:
        model_name = model_name.strip()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/api/generate",
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.8,
                            "num_predict": 300,
                        },
                    },
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    text = resp.json().get("response", "")
                    if text:
                        print(f"[Ollama/{model_name}] ✓ Response received ({len(text)} chars)")
                        return text
                else:
                    print(f"[Ollama/{model_name}] ✗ HTTP {resp.status_code}")
                    continue
        except httpx.ConnectError:
            print(f"[Ollama] ✗ Server not running at {base_url}")
            return None  # No point trying other models if server is down
        except Exception as e:
            print(f"[Ollama/{model_name}] ✗ Error: {e}")
            continue

    return None


async def _call_llm_cascade(prompt: str) -> Tuple[Optional[str], str]:
    """
    Calls LLM providers in cascade order: Gemini → Groq → Ollama.
    Returns (response_text, provider_name) or (None, "none").
    """
    # 1. Try Gemini first
    result = await _call_gemini(prompt)
    if result:
        return result, "gemini"

    # 2. Try Groq
    result = await _call_groq(prompt)
    if result:
        return result, "groq"

    # 3. Try Ollama (local)
    result = await _call_ollama(prompt)
    if result:
        return result, "ollama"

    return None, "none"


# ──────────────────────────────────────────────────────────────────────────────
# JSON RESPONSE CLEANER
# ──────────────────────────────────────────────────────────────────────────────

def clean_json_response(response_text: str) -> str:
    """
    Extracts valid JSON from an LLM response that may include:
    - Markdown code fences (```json ... ```)
    - Explanatory text before/after the JSON
    - Invalid JSON: +5 (should be 5), trailing commas, etc.
    Works with Gemini, Groq (Llama), and Ollama outputs.
    """
    cleaned = response_text.strip()

    # 1. Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    # 2. Fix common LLM JSON quirks
    #    - "+5" → "5" (Llama/Groq outputs positive integers with + prefix)
    cleaned = re.sub(r':\s*\+(\d+)', r': \1', cleaned)
    #    - Trailing commas before closing brace/bracket
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    # 3. Try parsing as-is first
    try:
        json.loads(cleaned)
        return cleaned
    except (json.JSONDecodeError, ValueError):
        pass

    # 4. Extract JSON object from surrounding text using brace matching
    first_brace = cleaned.find("{")
    if first_brace != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(first_brace, len(cleaned)):
            c = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[first_brace:i + 1]
                    # Apply fixes to extracted candidate too
                    candidate = re.sub(r':\s*\+(\d+)', r': \1', candidate)
                    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                    try:
                        json.loads(candidate)
                        return candidate
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    # 5. Last resort: return cleaned text and let caller handle the error
    return cleaned


# ──────────────────────────────────────────────────────────────────────────────
# PERSONALITY-DRIVEN PROMPT BUILDER (The Core Innovation)
# ──────────────────────────────────────────────────────────────────────────────

def _build_personality_prompt(
    student_name: str,
    personality_profile: Dict[str, Any],
    state: StudentState,
    memory: Dict[str, Any],
    classroom_state: Dict[str, Any],
    teacher_message: str,
    conversation_history: List[Dict[str, str]],
    session_info: Dict[str, str],
) -> str:
    """
    Builds a UNIQUE prompt for each student based on their personality DNA.
    This is what makes Aarav, Ananya, and Kabir respond completely differently.
    """
    traits = personality_profile["traits"]
    patterns = personality_profile["speech_patterns"]
    rules = personality_profile["behavior_rules"]
    grade_key = get_grade_key(session_info["class_level"])
    grade_style = personality_profile["grade_adaptation"].get(grade_key, "")

    # Format memory context
    memory_context = format_memory_for_prompt(memory)

    # Format recent conversation (last 8 turns)
    history_lines = []
    for msg in conversation_history[-8:]:
        sender = msg.get("sender_name", msg.get("sender_type", "Unknown"))
        text = msg.get("message_text", "")
        history_lines.append(f"  {sender}: {text}")
    history_str = "\n".join(history_lines) if history_lines else "  (Class just started, no conversation yet)"

    # Build speech patterns string
    patterns_str = "\n".join(f"  • {p}" for p in patterns)

    # Build behavior rules string
    rules_str = "\n".join(f"  • {r}" for r in rules)

    # Calculate dynamic classroom mood adaptations
    mood_alerts = []
    class_attention = classroom_state.get("attention", classroom_state.get("avg_class_attention", 75.0))
    class_confusion = classroom_state.get("confusion", classroom_state.get("avg_class_confusion", 25.0))

    if class_attention < 50.0:
        if student_name.lower() == "vihaan":
            mood_alerts.append(f"• ATTENTION ALERT ({class_attention}%): The classroom's average attention is low. You are extremely bored, zoned out, and distracted. Doodles, daydream, whisper, or give completely distracted, off-topic responses or just say 'Huh? Wait, what?'.")
        elif student_name.lower() == "kabir":
            mood_alerts.append(f"• ATTENTION ALERT ({class_attention}%): The classroom's average attention is low. You are bored and restless. Interrupt the teacher or other students, bragging or acting cocky about what you already know.")

    if class_confusion > 55.0:
        if student_name.lower() == "riya":
            mood_alerts.append(f"• CONFUSION ALERT ({class_confusion}%): The classroom is highly confused. You are feeling completely lost. Ask a simple, basic clarification question (e.g., 'I don't get it', 'What does that word mean?', 'Could you explain again?').")
        elif student_name.lower() == "ananya":
            mood_alerts.append(f"• CONFUSION ALERT ({class_confusion}%): The classroom is highly confused. You are feeling overwhelmed, insecure, and extremely timid. Stay completely quiet. If forced to speak, give a highly hesitant, quiet, one-word response or just trail off with '...'")

    mood_alerts_str = "\n".join(mood_alerts) if mood_alerts else "  • Class is balanced. Maintain normal character behaviors."

    ds = memory.get("dynamic_state", {})
    stress = ds.get("stress", 15.0)
    mood = ds.get("mood", "normal")
    relationships = memory.get("relationships", {})
    
    # Format relationships text for prompt injection
    relationships_str = ""
    if relationships:
        rel_lines = []
        for peer, info in relationships.items():
            if isinstance(info, dict) and "trust" in info:
                rel_lines.append(
                    f"    - {peer}: Trust={round(info.get('trust', 50.0), 1)}/100, "
                    f"Friendship={round(info.get('friendship', 50.0), 1)}/100, "
                    f"Annoyance={round(info.get('annoyance', 10.0), 1)}/100, "
                    f"Influence={round(info.get('influence', 30.0), 1)}/100, "
                    f"Supportiveness={round(info.get('supportiveness', 50.0), 1)}/100"
                )
            else:
                strength = info.get('strength', 1.0) if isinstance(info, dict) else 1.0
                rel_lines.append(f"    - {peer}: dynamic relationship strength multiplier: {round(strength, 2)}x")
        relationships_str = "\n".join(rel_lines)
    else:
        relationships_str = "    - No significant relationship influences active."

    return f"""You are {student_name}, a REAL {grade_key} school student in an Indian classroom.
You are NOT an AI. You are a specific child with specific habits, fears, quirks, and ways of talking.

═══ YOUR PERSONALITY DNA (this defines WHO you are — never break character) ═══
Role: {personality_profile["role"]}
Curiosity: {traits["curiosity"]}/100
Confidence: {traits["confidence"]}/100
Current Attention: {state.attention_level}/100
Current Confusion: {state.confusion_level}/100
Current Understanding: {state.understanding_level}/100
Current Stress: {round(stress, 1)}/100
Current Mood: {mood}
Active Peer Relationships & Copying Influences:
{relationships_str}
Times you've spoken today: {state.participation_count}

═══ HOW YOU TALK (copy these speech patterns EXACTLY) ═══
{patterns_str}

═══ YOUR BEHAVIOR RULES (follow these strictly) ═══
{rules_str}

═══ FOR GRADE LEVEL: {session_info["class_level"]} ═══
{grade_style}

═══ WHAT YOU REMEMBER FROM THIS CLASS ═══
{memory_context}

═══ CLASSROOM RIGHT NOW ═══
Subject: {session_info["subject"]} | Topic: {session_info["topic"]}
Turn #{classroom_state["turn_number"]} | Energy: {classroom_state.get("energy", classroom_state.get("energy_level", "medium"))} | Engagement: {classroom_state.get("engagement", 70.0)}%
Class avg attention: {class_attention}% | Class avg confusion: {class_confusion}%

═══ DYNAMIC CLASS MOOD ADAPTATIONS (follow these immediately!) ═══
{mood_alerts_str}

═══ RECENT CONVERSATION ═══
{history_str}

═══ TEACHER JUST SAID ═══
"{teacher_message}"

═══ ABSOLUTE RULES (violating these = failure) ═══
1. You ARE {student_name}. Your personality traits above define your EXACT behavior. Do NOT act like any other student.
2. Keep response to 1-2 sentences MAX. Real kids don't give speeches or lectures.
3. Use the speech patterns listed above. Do NOT use formal/academic language like "fascinating", "correlation", "phenomenon".
4. Check "WHAT YOU REMEMBER" — NEVER repeat something you already said. NEVER ask about something already explained.
5. If your attention is below 40 → you might zone out, give off-topic response, or say "huh?"
6. If your confusion is above 60 → express genuine confusion in your character's way.
7. If teacher said a greeting → greet back in YOUR character's style. Don't start discussing the topic.
8. If teacher asked a question → attempt to answer (correctly/incorrectly based on your personality and understanding level).
10. Humanization & Imperfections: Real students speak with natural imperfections. Depending on your current understanding level (<65), confidence (<60), or confusion (>50), occasionally include realistic speech imperfections such as:
    - Hesitations/Fillers: "Umm...", "Uh...", "Ah...", "Wait...", "I think..."
    - Uncertainty: sounding unsure, questioning your own response
    - Changing confidence: correcting yourself midsentence or trailing off with "..."
    - Occasional minor mistakes: giving a slightly incorrect or incomplete explanation.
    Do NOT give textbook-perfect, clean answers unless your understanding is 100. Keep it subtle and natural.
9. Language: {session_info["language"]}. Use Devanagari for Hindi, Bengali script for Bengali, English for English.

Return ONLY raw JSON (no markdown, no ```json, just the object):
{{
    "response_text": "your 1-2 sentence response as {student_name}",
    "emotion": "normal|confused|questioning|sleeping|distracted|talking",
    "attention_change": -20 to +20,
    "confidence_change": -15 to +15,
    "understanding_change": -15 to +15,
    "confusion_change": -15 to +15,
    "memory_update": "one sentence: what {student_name} learned or felt this turn"
}}"""


# ──────────────────────────────────────────────────────────────────────────────
# PERSONALITY-AWARE FALLBACK RESPONSES
# ──────────────────────────────────────────────────────────────────────────────

def _generate_fallback_response(
    student_name: str,
    personality: str,
    teacher_message: str,
    topic: str,
    language: str,
    class_level: str,
    memory: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generates a personality-aware fallback when Gemini API is unavailable.
    Unlike the old system, each personality type has rich, varied templates
    that incorporate the actual topic and teacher's message.
    """
    t_lower = teacher_message.lower().strip("?!., ")
    topic_clean = topic.strip()
    grade_key = get_grade_key(class_level)

    # Check for greetings
    greetings = [
        "good morning", "good afternoon", "good evening", "hello", "hi", "hey",
        "namaste", "namaskar", "suprabhat", "shubho shokal", "kemon acho",
        "aap kaise hain", "how are you",
    ]
    is_greeting = any(g in t_lower and len(t_lower) < len(g) + 15 for g in greetings)

    # Check for questions
    is_question = teacher_message.strip().endswith("?") or any(
        w in t_lower for w in ["what", "why", "how", "who", "when", "explain", "tell"]
    )

    # Extract a keyword from teacher message for contextual responses
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                  "to", "for", "of", "and", "or", "but", "it", "this", "that",
                  "what", "why", "how", "can", "you", "we", "do", "does", "did",
                  "tell", "me", "about", "explain", "class", "today", "now"}
    words = [w for w in t_lower.split() if w not in stop_words and len(w) > 2]
    keyword = words[0] if words else topic_clean

    # Avoid repeating last responses
    last_responses = memory.get("last_responses", [])

    # Generate personality-specific response
    if language == "Hindi":
        responses = _hindi_fallback(student_name, personality, is_greeting, is_question, topic_clean, keyword, grade_key)
    elif language == "Bengali":
        responses = _bengali_fallback(student_name, personality, is_greeting, is_question, topic_clean, keyword, grade_key)
    else:
        responses = _english_fallback(student_name, personality, is_greeting, is_question, topic_clean, keyword, grade_key)

    # Filter out any responses that match recent ones
    available = [r for r in responses if r not in last_responses]
    if not available:
        available = responses

    response_text = random.choice(available)

    # Determine emotion
    emotion_map = {
        "Curious student": "questioning",
        "Shy student": random.choice(["normal", "normal", "distracted"]),
        "Distracted student": random.choice(["distracted", "sleeping", "distracted"]),
        "Hyperactive student": "talking",
        "Weak learner": random.choice(["confused", "confused", "normal"]),
        "Overconfident student": "talking",
    }
    emotion = emotion_map.get(personality, "normal")

    return {
        "responding_student": student_name,
        "response_text": response_text,
        "emotion": emotion,
    }


def _english_fallback(name, personality, is_greeting, is_question, topic, keyword, grade):
    """English fallback responses per personality."""
    if is_greeting:
        return {
            "Curious student": [
                f"Good morning, teacher! I was looking up {topic} last night — can't wait!",
                f"Morning! I have so many questions about {topic} already!",
            ],
            "Shy student": [
                "Good morning... (nods quietly)",
                "...morning, teacher. (looks down)",
            ],
            "Distracted student": [
                "Oh! Morning! (scrambles to put notebook away)",
                "Huh? Oh, good morning! Sorry, I was drawing...",
            ],
            "Hyperactive student": [
                f"GOOD MORNING TEACHER!! Are we doing {topic} today?! I'm SO excited!!",
                f"Morning!! Can we start already?! I wanna learn about {topic}!!",
            ],
            "Weak learner": [
                f"Good morning teacher! I hope {topic} won't be too hard today...",
                "Morning! Can we go slow today please?",
            ],
            "Overconfident student": [
                f"Morning! I already studied {topic} — you can quiz me anytime!",
                f"Good morning! Pfft, {topic}? I already know all of this.",
            ],
        }.get(personality, [f"Good morning, teacher!"])

    if is_question:
        return {
            "Curious student": [
                f"Hmm, I think it's related to {keyword}... but wait, what if it's different for other cases?",
                f"Oh! Is it because of {keyword}? I read something about this!",
            ],
            "Shy student": [
                f"Um... maybe... {keyword}...? I'm not sure sorry...",
                "I... I think I know but... (trails off)",
            ],
            "Distracted student": [
                f"Wait, what was the question? Something about {keyword}?",
                "Sorry, I wasn't listening... can you ask again?",
            ],
            "Hyperactive student": [
                f"OH! I KNOW! It's {keyword}!! Right?! RIGHT?!",
                f"PICK ME! It's because of {keyword}!! I saw it on YouTube!",
            ],
            "Weak learner": [
                f"Is it... {keyword}? I'm not really sure what that means though...",
                f"I don't really get {keyword}... can you explain it simpler?",
            ],
            "Overconfident student": [
                f"Obviously it's {keyword}. Everyone knows that. Easy.",
                f"Pfft, the answer is clearly {keyword}. I knew this already.",
            ],
        }.get(personality, [f"I think it might be {keyword}..."])

    # General response to explanation
    return {
        "Curious student": [
            f"But wait, how does {keyword} actually work? Like, what happens inside?",
            f"That's cool! But what if {keyword} was different? Would it change everything?",
        ],
        "Shy student": [
            "...okay... (writes in notebook quietly)",
            f"Um... I think I understand the {keyword} part... maybe...",
        ],
        "Distracted student": [
            f"Wait, are we still on {keyword}? I lost track...",
            "Sorry, what page are we on? I was looking at something...",
        ],
        "Hyperactive student": [
            f"Can we DO something with {keyword}?! Like an experiment?!",
            f"OH that's SO COOL! {keyword} is amazing!! What else?!",
        ],
        "Weak learner": [
            f"Teacher, I'm lost... what is {keyword} again?",
            f"Can you explain {keyword} with a simple example? I don't get it...",
        ],
        "Overconfident student": [
            f"Yeah, I already knew about {keyword}. My brother told me last week.",
            f"That's basic stuff. {keyword} is easy — what's next?",
        ],
    }.get(personality, [f"I see, so it's about {keyword}..."])


def _hindi_fallback(name, personality, is_greeting, is_question, topic, keyword, grade):
    """Hindi fallback responses per personality."""
    if is_greeting:
        return {
            "Curious student": [f"सुप्रभात शिक्षक! {topic} के बारे में बहुत excited हूँ!", f"नमस्ते! आज {topic} पढ़ेंगे ना? मैंने कल रात कुछ पढ़ा!"],
            "Shy student": ["नमस्ते... (धीरे से सिर झुकाती है)", "...सुप्रभात सर। (नीचे देखती है)"],
            "Distracted student": ["अरे! सुप्रभात! (जल्दी से कॉपी बंद करता है)", "ओह! नमस्ते सर! माफ़ करना, मैं drawing कर रहा था..."],
            "Hyperactive student": [f"सुप्रभात शिक्षक जी!! आज {topic} में experiment करेंगे?! बहुत excited हूँ!!", f"नमस्ते!! शुरू करें ना!! {topic} सीखना है!!"],
            "Weak learner": [f"सुप्रभात सर! उम्मीद है आज {topic} ज़्यादा मुश्किल नहीं होगा...", "नमस्ते! आज धीरे-धीरे पढ़ाइएगा प्लीज़?"],
            "Overconfident student": [f"सुप्रभात! मैंने {topic} कल ही पढ़ लिया — कोई भी सवाल पूछ लीजिए!", f"नमस्ते! {topic}? यह तो बहुत आसान है!"],
        }.get(personality, ["सुप्रभात शिक्षक जी!"])

    if is_question:
        return {
            "Curious student": [f"मुझे लगता है यह {keyword} से जुड़ा है... लेकिन रुकिए, अगर अलग situation हो तो?", f"ओह! क्या यह {keyword} की वजह से होता है?"],
            "Shy student": [f"उम... शायद... {keyword}...? मुझे पक्का नहीं पता... माफ़ कीजिए...", "मुझे... मुझे लगता है पता है पर... (चुप हो जाती है)"],
            "Distracted student": [f"रुकिए, सवाल क्या था? {keyword} के बारे में कुछ?", "माफ़ करना, मैं सुन नहीं रहा था... दोबारा पूछेंगे?"],
            "Hyperactive student": [f"सर! मुझे पता है! {keyword}!! है ना?! है ना?!", f"मुझे choose करो! {keyword} की वजह से! YouTube पर देखा था!"],
            "Weak learner": [f"क्या यह... {keyword} है? मुझे सच में समझ नहीं आया...", f"{keyword} का मतलब क्या है? आसान शब्दों में बताइए ना..."],
            "Overconfident student": [f"बिल्कुल {keyword} है। सबको पता है। बहुत आसान।", f"इसका जवाब तो {keyword} है। मुझे पहले से पता था।"],
        }.get(personality, [f"शायद {keyword}... मुझे नहीं पता"])

    return {
        "Curious student": [f"लेकिन रुकिए, {keyword} अंदर से कैसे काम करता है?", f"यह तो मज़ेदार है! अगर {keyword} अलग हो तो क्या होगा?"],
        "Shy student": ["...ठीक है... (चुपचाप कॉपी में लिखती है)", f"उम... मुझे {keyword} वाला हिस्सा समझ आया... शायद..."],
        "Distracted student": [f"रुकिए, हम अभी भी {keyword} पर हैं? मैं भूल गया...", "माफ़ करना, कौन सा page है? मैं कुछ और देख रहा था..."],
        "Hyperactive student": [f"क्या हम {keyword} के साथ कुछ बना सकते हैं?! Experiment!!", f"यह तो बहुत COOL है! {keyword} amazing है!!"],
        "Weak learner": [f"सर, मैं confused हूँ... {keyword} क्या है?", f"क्या {keyword} को आसान example से समझा सकते हैं?"],
        "Overconfident student": [f"हाँ, मुझे {keyword} पहले से पता है। भाई ने बताया था।", f"यह तो basic है। {keyword} आसान है — आगे बढ़िए।"],
    }.get(personality, [f"हम्म, तो {keyword} के बारे में..."])


def _bengali_fallback(name, personality, is_greeting, is_question, topic, keyword, grade):
    """Bengali fallback responses per personality."""
    if is_greeting:
        return {
            "Curious student": [f"শুভ সকাল স্যার! {topic} নিয়ে খুব excited!", f"নমস্কার! আজ {topic} পড়ব তো?"],
            "Shy student": ["নমস্কার... (ধীরে মাথা নিচু করে)", "...শুভ সকাল স্যার। (নিচে তাকিয়ে)"],
            "Distracted student": ["ওহ! শুভ সকাল! (তাড়াতাড়ি খাতা বন্ধ করে)", "নমস্কার স্যার! মাফ করবেন, আঁকছিলাম..."],
            "Hyperactive student": [f"শুভ সকাল স্যার!! {topic} নিয়ে experiment করব?! খুব excited!!", f"নমস্কার!! শুরু করি!! {topic} শিখতে চাই!!"],
            "Weak learner": [f"শুভ সকাল স্যার! আশা করি {topic} খুব কঠিন হবে না...", "নমস্কার! আজ আস্তে আস্তে পড়াবেন প্লিজ?"],
            "Overconfident student": [f"শুভ সকাল! {topic} গতকালই পড়ে ফেলেছি — যেকোনো প্রশ্ন করুন!", f"নমস্কার! {topic}? এটা তো খুব সহজ!"],
        }.get(personality, ["শুভ সকাল স্যার!"])

    if is_question:
        return {
            "Curious student": [f"আমার মনে হয় এটা {keyword}-এর সাথে জড়িত... কিন্তু অন্য situation-এ?", f"ওহ! এটা কি {keyword}-এর জন্য হয়?"],
            "Shy student": [f"উম... হয়তো... {keyword}...? আমি নিশ্চিত নই... দুঃখিত...", "আমার... মনে হয় জানি কিন্তু... (চুপ হয়ে যায়)"],
            "Distracted student": [f"দাঁড়ান, প্রশ্নটা কী ছিল? {keyword} নিয়ে?", "মাফ করবেন, শুনছিলাম না... আবার বলবেন?"],
            "Hyperactive student": [f"স্যার! আমি জানি! {keyword}!! তাই না?! তাই না?!", f"আমাকে বলতে দিন! {keyword}! YouTube-এ দেখেছিলাম!"],
            "Weak learner": [f"এটা কি... {keyword}? আমি সত্যিই বুঝতে পারছি না...", f"{keyword} মানে কী? সহজ করে বলুন না..."],
            "Overconfident student": [f"অবশ্যই {keyword}। সবাই জানে। খুব সহজ।", f"উত্তর তো {keyword}। আমি আগেই জানতাম।"],
        }.get(personality, [f"হয়তো {keyword}..."])

    return {
        "Curious student": [f"কিন্তু দাঁড়ান, {keyword} ভেতরে কীভাবে কাজ করে?", f"মজার! {keyword} যদি আলাদা হত তাহলে কী হত?"],
        "Shy student": ["...ঠিক আছে... (চুপচাপ খাতায় লেখে)", f"উম... {keyword} অংশটা বুঝেছি... মনে হয়..."],
        "Distracted student": [f"দাঁড়ান, এখনো {keyword} নিয়ে? ভুলে গেছি...", "মাফ করবেন, কোন পেজ? অন্যকিছু দেখছিলাম..."],
        "Hyperactive student": [f"{keyword} দিয়ে কিছু বানাতে পারি?! Experiment!!", f"এটা তো দারুণ! {keyword} অসাধারণ!!"],
        "Weak learner": [f"স্যার, confused... {keyword} কী?", f"{keyword} সহজ example দিয়ে বোঝাবেন?"],
        "Overconfident student": [f"হ্যাঁ, {keyword} আমি আগে থেকেই জানি। দাদা বলেছিল।", f"এটা basic। {keyword} সহজ — পরেরটা বলুন।"],
    }.get(personality, [f"হুম, {keyword} সম্পর্কে..."])


# ──────────────────────────────────────────────────────────────────────────────
# MAIN STUDENT REPLY GENERATOR
# ──────────────────────────────────────────────────────────────────────────────

async def generate_student_reply(
    session_id: int,
    db: DBSession,
    subject: str,
    topic: str,
    class_level: str,
    objectives: str,
    method: str,
    language: str,
    student_name: str,
    student_personality: str,
    teacher_message: str,
    conversation_history: List[Dict[str, str]],
    active_event: Optional[str] = None,
    is_interrupt: bool = False,
) -> Dict[str, Any]:
    """
    Generates a student response using personality-driven prompts.
    Uses Gemini 2.0 Flash with per-student personality profiles.
    Falls back to personality-aware templates if API is unavailable.
    """
    language = str(language).strip().title()

    # Get or create student state
    state_rec = db.query(StudentState).filter(
        StudentState.session_id == session_id,
        StudentState.student_name == student_name,
    ).first()

    if not state_rec:
        # Initialize with personality-driven defaults
        personality_profile = STUDENT_PERSONALITIES.get(student_name, {})
        traits = personality_profile.get("traits", {})
        state_rec = StudentState(
            session_id=session_id,
            student_name=student_name,
            attention_level=traits.get("attention_base", 75),
            confidence_level=traits.get("confidence", 65),
            understanding_level=75,
            confusion_level=traits.get("confusion_base", 25),
            curiosity_level=traits.get("curiosity", 50),
            interrupt_probability=traits.get("interrupt_probability", 20),
            memory_summary=f"Class started. Topic: {topic}.",
            memory_json=json.dumps({
                "concepts_taught": [],
                "questions_asked_by_student": [],
                "questions_received_from_teacher": [],
                "key_interactions": [],
                "last_responses": [],
            }),
            participation_count=0,
        )
        db.add(state_rec)
        db.commit()
        db.refresh(state_rec)

    # Get structured memory
    memory = get_student_memory(state_rec)

    # Get personality profile
    personality_profile = STUDENT_PERSONALITIES.get(student_name)

    # Session info
    session_info = {
        "subject": subject,
        "topic": topic,
        "class_level": class_level,
        "objectives": objectives,
        "method": method,
        "language": language,
    }

    # Compute classroom state
    all_states = db.query(StudentState).filter(
        StudentState.session_id == session_id
    ).all()
    turn_number = len(conversation_history)

    from personality import compute_classroom_state
    classroom_state = compute_classroom_state(
        turn_number=turn_number,
        session_duration_minutes=15,
        student_states=all_states,
    )

    # ── Try LLM Cascade: Gemini → Groq → Ollama ──
    if personality_profile:
        try:
            prompt = _build_personality_prompt(
                student_name=student_name,
                personality_profile=personality_profile,
                state=state_rec,
                memory=memory,
                classroom_state=classroom_state,
                teacher_message=teacher_message,
                conversation_history=conversation_history,
                session_info=session_info,
            )

            print(f"[AI] Generating reply for {student_name} ({student_personality})...")
            response_content, provider = await _call_llm_cascade(prompt)

            if response_content:
                cleaned = clean_json_response(response_content)
                parsed = json.loads(cleaned)
                
                # Validate response uniqueness using SimulationValidationEngine
                from validation import SimulationValidationEngine
                st = memory.get("short_term", {})
                last_responses = st.get("last_responses", [])
                raw_response = parsed.get("response_text", "")
                
                healed_text = SimulationValidationEngine.validate_and_heal_response(
                    student_name=student_name,
                    personality_role=personality_profile.get("role", "Curious student"),
                    response_text=raw_response,
                    last_responses=last_responses,
                    topic=topic
                )
                parsed["response_text"] = healed_text
                
                print(f"[AI] ✓ via {provider}: student={student_name}, emotion={parsed.get('emotion')}, text={parsed.get('response_text', '')[:80]}...")

                # Update student state from AI deltas
                state_rec.attention_level = max(0, min(100,
                    state_rec.attention_level + parsed.get("attention_change", 0)))
                state_rec.confidence_level = max(0, min(100,
                    state_rec.confidence_level + parsed.get("confidence_change", 0)))
                state_rec.understanding_level = max(0, min(100,
                    state_rec.understanding_level + parsed.get("understanding_change", 0)))
                state_rec.confusion_level = max(0, min(100,
                    state_rec.confusion_level + parsed.get("confusion_change", 0)))
                state_rec.participation_count += 1

                # Update legacy memory summary
                if parsed.get("memory_update"):
                    state_rec.memory_summary = parsed["memory_update"]

                # Update structured memory
                update_student_memory(
                    state=state_rec,
                    memory=memory,
                    response_text=parsed.get("response_text", ""),
                    teacher_message=teacher_message,
                    memory_update_text=parsed.get("memory_update", ""),
                    turn_number=turn_number,
                    is_interrupt=is_interrupt,
                )

                db.commit()

                return {
                    "responding_student": student_name,
                    "response_text": parsed.get("response_text", ""),
                    "emotion": parsed.get("emotion", "normal"),
                    "fallback_activated": False
                }

        except json.JSONDecodeError as e:
            print(f"[AI] ✗ JSON parse error from {provider}: {e}")
        except Exception as e:
            print(f"[AI] ✗ LLM cascade error for {student_name}: {e}")

    # ── Final Fallback: Personality-aware template responses ──
    print(f"[AI] Using template fallback for {student_name}")
    fallback = _generate_fallback_response(
        student_name=student_name,
        personality=student_personality,
        teacher_message=teacher_message,
        topic=topic,
        language=language,
        class_level=class_level,
        memory=memory,
    )

    # Heal repetitive fallback response
    from validation import SimulationValidationEngine
    st = memory.get("short_term", {})
    last_responses = st.get("last_responses", [])
    healed_fallback = SimulationValidationEngine.validate_and_heal_response(
        student_name=student_name,
        personality_role=student_personality,
        response_text=fallback["response_text"],
        last_responses=last_responses,
        topic=topic
    )
    fallback["response_text"] = healed_fallback

    # Update memory even in fallback
    update_student_memory(
        state=state_rec,
        memory=memory,
        response_text=fallback["response_text"],
        teacher_message=teacher_message,
        memory_update_text=f"Responded to teacher about {topic}",
        turn_number=turn_number,
        is_interrupt=is_interrupt,
    )
    state_rec.participation_count += 1
    db.commit()

    fallback["fallback_activated"] = True
    return fallback


# ──────────────────────────────────────────────────────────────────────────────
# EVIDENCE-BASED EVALUATION SYSTEM
# ──────────────────────────────────────────────────────────────────────────────

def _compute_session_metrics(
    transcript: List[Dict[str, str]],
    student_states: List[StudentState],
) -> Dict[str, Any]:
    """
    Computes real, evidence-based metrics from the actual session data.
    These numbers are REAL — computed from DB records, not guessed by an LLM.
    """
    from datetime import datetime
    import re

    def parse_ts(ts_str):
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str)
        except Exception:
            return None

    teacher_messages = [m for m in transcript if m["sender_type"] == "teacher"]
    student_messages = [m for m in transcript if m["sender_type"] == "student"]
    system_messages = [m for m in transcript if m["sender_type"] == "system"]

    teacher_words = sum(len(m["message_text"].split()) for m in teacher_messages)
    student_words = sum(len(m["message_text"].split()) for m in student_messages)
    total_words = teacher_words + student_words

    # Unique students who spoke
    unique_speakers = set(m["sender_name"] for m in student_messages)
    all_students = {"Aarav", "Ananya", "Vihaan", "Ishaan", "Riya", "Kabir"}
    never_addressed = all_students - unique_speakers

    # Students mentioned by teacher and teacher questions
    addressed_by_teacher = set()
    teacher_questions = 0
    for m in teacher_messages:
        text_lower = m["message_text"].lower()
        if text_lower.strip().endswith("?") or any(w in text_lower for w in ["what", "why", "how", "who"]):
            teacher_questions += 1
        for name in all_students:
            if name.lower() in text_lower:
                addressed_by_teacher.add(name)

    # ──── TEACHER SPEAKING STYLE ANALYSIS ────
    teacher_filler_count = 0
    teacher_open_questions = 0
    teacher_total_duration = 0.0
    teacher_total_words = 0

    for i, m in enumerate(transcript):
        if m["sender_type"] == "teacher":
            text = m["message_text"]
            words = text.split()
            word_count = len(words)
            teacher_total_words += word_count

            # Count standard filler words/phrases case-insensitively as distinct units
            fillers = re.findall(r'\b(um|uh|uhm|er|ah|like|actually|you\s+know)\b', text.lower())
            teacher_filler_count += len(fillers)

            # Count open-ended questions: ends in ? or contains ? and uses open words
            if text.strip().endswith("?") or "?" in text:
                is_open = any(q_word in text.lower() for q_word in ["why", "how", "explain", "what do you think", "describe", "elaborate", "tell me"])
                if is_open:
                    teacher_open_questions += 1

            # Determine turn duration using timestamp difference
            turn_duration = 0.0
            ts_curr = parse_ts(m.get("timestamp"))
            if ts_curr and i + 1 < len(transcript):
                ts_next = parse_ts(transcript[i+1].get("timestamp"))
                if ts_next:
                    diff = (ts_next - ts_curr).total_seconds()
                    # Bound turn duration to a realistic limit (1.5s to 300s)
                    if 1.5 <= diff <= 300.0:
                        turn_duration = diff

            # Fallback to estimated speaking rate if timestamp difference is missing/invalid
            if turn_duration == 0.0:
                turn_duration = max(2.5, word_count / 2.17)  # 130 WPM is ~2.17 words per second

            teacher_total_duration += turn_duration

    # Calculate average Words Per Minute (WPM)
    teacher_wpm = round((teacher_total_words / max(1.0, teacher_total_duration)) * 60, 1)

    # Student state averages
    avg_attention = sum(s.attention_level for s in student_states) / max(1, len(student_states))
    avg_confusion = sum(s.confusion_level for s in student_states) / max(1, len(student_states))
    avg_understanding = sum(s.understanding_level for s in student_states) / max(1, len(student_states))

    # Most/least engaged
    most_engaged = max(student_states, key=lambda s: s.participation_count).student_name if student_states else "N/A"
    most_confused = max(student_states, key=lambda s: s.confusion_level).student_name if student_states else "N/A"
    least_engaged = min(student_states, key=lambda s: s.participation_count).student_name if student_states else "N/A"

    return {
        "total_turns": len(transcript),
        "teacher_turns": len(teacher_messages),
        "student_turns": len(student_messages),
        "events_triggered": len(system_messages),
        "teacher_speaking_pct": round(teacher_words / max(1, total_words) * 100, 1),
        "student_speaking_pct": round(student_words / max(1, total_words) * 100, 1),
        "teacher_word_count": teacher_words,
        "student_word_count": student_words,
        "unique_students_engaged": len(unique_speakers),
        "students_never_addressed": list(never_addressed),
        "students_addressed_by_teacher": list(addressed_by_teacher),
        "teacher_questions_asked": teacher_questions,
        "teacher_filler_count": teacher_filler_count,
        "teacher_open_questions": teacher_open_questions,
        "teacher_wpm": teacher_wpm,
        "teacher_total_duration": round(teacher_total_duration, 1),
        "avg_student_attention": round(avg_attention, 1),
        "avg_student_confusion": round(avg_confusion, 1),
        "avg_student_understanding": round(avg_understanding, 1),
        "most_engaged_student": most_engaged,
        "most_confused_student": most_confused,
        "least_engaged_student": least_engaged,
    }


def _compute_adaptability_score(
    transcript: List[Dict[str, str]],
    student_states: List[StudentState],
) -> Dict[str, Any]:
    """
    Computes a Teacher Adaptability Score (0-10) and feedback by analyzing:
    1. Response to student confusion events (scaffold/explain actions after confusion)
    2. Adjustment of speaking pace (WPM corrections)
    3. Handling classroom interruptions (whispering / late entries focus actions)
    4. Encouraging participation from silent/shy students (e.g. Ananya)
    5. Shifting strategies (using blackboard, modes etc.)
    """
    teacher_messages = [m for m in transcript if m["sender_type"] == "teacher"]
    
    # 1. Responded to confusion (scaffold/explain_basic after confusion events or student confusion phrases)
    confusion_events = 0
    confusion_resolved = 0
    
    for idx, m in enumerate(transcript):
        is_confusion = False
        if m["sender_type"] == "system" and "confusion" in m["sender_name"].lower():
            is_confusion = True
        elif m["sender_type"] == "student" and any(w in m["message_text"].lower() for w in ["confused", "don't understand", "unclear", "explain again", "what does"]):
            is_confusion = True
            
        if is_confusion:
            confusion_events += 1
            next_teacher = None
            for next_m in transcript[idx+1:]:
                if next_m["sender_type"] == "teacher":
                    next_teacher = next_m
                    break
            if next_teacher:
                msg_lower = next_teacher["message_text"].lower()
                if "explain" in msg_lower or "scaffold" in msg_lower or "blackboard" in msg_lower or "[" in msg_lower or "analogy" in msg_lower:
                    confusion_resolved += 1
                    
    conf_score = 10.0 if confusion_events == 0 else (confusion_resolved / confusion_events) * 10.0

    # 2. Adjusted speaking pace (shorter messages after long ones)
    pace_turns = 0
    pace_adjusted = 0
    for i in range(len(teacher_messages) - 1):
        words_curr = len(teacher_messages[i]["message_text"].split())
        words_next = len(teacher_messages[i+1]["message_text"].split())
        
        if words_curr > 45:
            pace_turns += 1
            if words_next <= 35:
                pace_adjusted += 1
                
    pace_score = 10.0 if pace_turns == 0 else (pace_adjusted / pace_turns) * 10.0

    # 3. Handled interruptions (focus/warn action after whispering/interruption event)
    interruption_events = 0
    interruption_resolved = 0
    for idx, m in enumerate(transcript):
        if m["sender_type"] == "system" and any(word in m["sender_name"].lower() for word in ["whisper", "interrupt", "late", "drop"]):
            interruption_events += 1
            next_teacher = None
            for next_m in transcript[idx+1:]:
                if next_m["sender_type"] == "teacher":
                    next_teacher = next_m
                    break
            if next_teacher:
                msg_lower = next_teacher["message_text"].lower()
                if "[" in msg_lower or any(name.lower() in msg_lower for name in ["vihaan", "ishaan", "kabir", "ananya", "riya", "aarav"]):
                    interruption_resolved += 1
                    
    interruption_score = 10.0 if interruption_events == 0 else (interruption_resolved / interruption_events) * 10.0

    # 4. Encouraged participation (addressing Ananya or Riya)
    addressed_students = set()
    for m in teacher_messages:
        text_lower = m["message_text"].lower()
        for name in ["Ananya", "Riya"]:
            if name.lower() in text_lower:
                addressed_students.add(name)
                
    participation_score = 5.0 + len(addressed_students) * 2.5

    # 5. Changed Strategy (blackboard usage or question density)
    strategy_score = 5.0
    has_blackboard = any("blackboard" in m["message_text"].lower() or "[" in m["message_text"].lower() for m in teacher_messages)
    if has_blackboard:
        strategy_score += 3.0
    
    questions_asked = sum(1 for m in teacher_messages if "?" in m["message_text"])
    if questions_asked >= 3:
        strategy_score += 2.0

    # Calculate overall adaptability
    overall_score = round((conf_score + pace_score + interruption_score + participation_score + strategy_score) / 5.0, 1)

    # Formulate feedback text
    feedbacks = []
    if conf_score < 7.0:
        feedbacks.append("Teacher should focus on adjusting explanations more effectively when student confusion increases (e.g., using simpler scaffolding or blackboard drawings).")
    if interruption_score < 7.0:
        feedbacks.append("Consider responding more directly to classroom disruptions and whispering using refocus actions.")
    if participation_score < 7.0:
        feedbacks.append("Try to actively engage quiet or shy students like Ananya to balance participation.")
        
    if not feedbacks:
        feedbacks.append("Teacher adjusted explanations effectively after confusion increased, managed pacing, and engaged students successfully.")
        
    feedback_text = " ".join(feedbacks)

    return {
        "score": overall_score,
        "feedback": feedback_text
    }


def _compute_realism_score(
    transcript: List[Dict[str, str]],
    student_states: List[StudentState],
) -> Dict[str, Any]:
    """
    Computes a pedagogical and social Realism Score (0-10) and checks for session weaknesses.
    Factors: behavior diversity, memory consistency, response uniqueness, emotional smoothness, interaction quality.
    """
    import math
    import re
    from validation import compute_jaccard_similarity
    
    student_messages = [m for m in transcript if m["sender_type"] == "student"]
    teacher_messages = [m for m in transcript if m["sender_type"] == "teacher"]
    system_messages = [m for m in transcript if m["sender_type"] == "system"]
    
    # 1. Diversity Score (Shannon Entropy of speaker turns)
    speaker_counts = {}
    for m in student_messages:
        name = m.get("sender_name", "")
        speaker_counts[name] = speaker_counts.get(name, 0) + 1
        
    counts = list(speaker_counts.values())
    if counts:
        total = sum(counts)
        entropy = 0.0
        for c in counts:
            p = c / total
            entropy -= p * math.log2(p)
        # Max entropy for 6 students is log2(6) = 2.58
        div_score = min(10.0, (entropy / 2.58) * 10.0)
    else:
        div_score = 5.0
        
    # 2. Response Uniqueness (TTR checking)
    all_words = []
    for m in student_messages:
        words = re.findall(r'\w+', m["message_text"].lower())
        all_words.extend(words)
        
    if all_words:
        ttr = len(set(all_words)) / len(all_words)
        uniq_score = min(10.0, (ttr / 0.45) * 10.0)
    else:
        uniq_score = 5.0
        
    # 3. Memory Consistency (checking repetitions)
    repeat_deductions = 0
    for i in range(len(student_messages) - 1):
        t1 = student_messages[i]["message_text"]
        t2 = student_messages[i+1]["message_text"]
        if compute_jaccard_similarity(t1, t2) >= 0.8:
            repeat_deductions += 2.5
    cons_score = max(0.0, 10.0 - repeat_deductions)
    
    # 4. Emotional Smoothness (Standard deviation checks showing individual traits)
    if student_states:
        att_vals = [s.attention_level for s in student_states]
        conf_vals = [s.confusion_level for s in student_states]
        
        def std_dev(vals):
            n = len(vals)
            if n <= 1:
                return 0.0
            mean = sum(vals) / n
            variance = sum((x - mean) ** 2 for x in vals) / (n - 1)
            return math.sqrt(variance)
            
        att_sd = std_dev(att_vals)
        conf_sd = std_dev(conf_vals)
        
        smooth_score = 10.0
        if att_sd < 5.0:
            smooth_score -= 2.0
        if conf_sd < 5.0:
            smooth_score -= 2.0
    else:
        smooth_score = 7.0
        
    # 5. Interaction Quality
    event_resolved_ratio = 1.0
    if system_messages:
        addressed = 0
        for sys_m in system_messages:
            sys_text = sys_m["message_text"].lower()
            for teach_m in teacher_messages:
                teach_text = teach_m["message_text"].lower()
                if any(w in teach_text for w in ["focus", "attention", "quiet", "listen", "blackboard"]):
                    addressed += 1
                    break
        event_resolved_ratio = addressed / len(system_messages)
    qual_score = 5.0 + event_resolved_ratio * 5.0
    
    overall_score = round((div_score + uniq_score + cons_score + smooth_score + qual_score) / 5.0, 1)
    
    # Compile weaknesses list
    weaknesses = []
    if div_score < 7.0:
        weaknesses.append("A single student dominated the classroom turns, reducing participation diversity.")
    if uniq_score < 6.0:
        weaknesses.append("Student vocabulary and sentence structures became repetitive over time.")
    if cons_score < 8.0:
        weaknesses.append("Direct response repetitions detected during the session.")
    if smooth_score < 8.0:
        weaknesses.append("Student emotional states clustered too closely without realistic individual differences.")
    if qual_score < 7.0:
        weaknesses.append("Classroom disruptions and random events were not effectively addressed by the teacher.")
        
    if not weaknesses:
        weaknesses.append("No significant weaknesses detected. The simulation demonstrated highly realistic student behaviors.")
        
    return {
        "score": overall_score,
        "weaknesses": weaknesses
    }


async def generate_evaluation(
    subject: str,
    topic: str,
    class_level: str,
    objectives: str,
    method: str,
    language: str,
    transcript: List[Dict[str, str]],
    student_states: Optional[List[StudentState]] = None,
) -> Dict[str, Any]:
    """
    Evaluates the teaching session using evidence-based metrics.
    Passes REAL data to Gemini so scores are grounded in actual performance.
    """
    # Compute real metrics
    metrics = _compute_session_metrics(transcript, student_states or [])

    # Build transcript string
    transcript_str = "\n".join(
        f"{m['sender_name']} ({m['sender_type']}): {m['message_text']}"
        for m in transcript
    )

    # Short session shortcut
    if metrics["teacher_turns"] < 3:
        return {
            "communication_score": 90,
            "engagement_score": 90,
            "time_management_score": 90,
            "question_handling_score": 90,
            "suggestions": (
                "### Great Start!\n"
                "This was a quick introductory session. You welcomed the class warmly! "
                "To get detailed B.Ed pedagogical feedback, continue the lesson by "
                "explaining concepts, asking questions, and engaging different students."
            ),
            "transcript_summary": f"Brief introduction for {subject} ({topic}). Teacher established positive rapport.",
        }

    # Compute adaptability score
    adaptability_res = _compute_adaptability_score(transcript, student_states or [])

    # Compute realism score
    realism_res = _compute_realism_score(transcript, student_states or [])

    # Try LLM cascade for evaluation
    try:
        prompt = f"""You are a B.Ed Teacher Training Assessor. Evaluate this virtual classroom session.

SESSION: {subject} — {topic} (Grade: {class_level})
Objectives: {objectives}
Method: {method}

═══ REAL SESSION METRICS (computed from actual data — use these, don't invent numbers) ═══
Total turns: {metrics["total_turns"]}
Teacher turns: {metrics["teacher_turns"]} | Student turns: {metrics["student_turns"]}
Teacher speaking: {metrics["teacher_speaking_pct"]}% | Student speaking: {metrics["student_speaking_pct"]}%
Teacher word count: {metrics["teacher_word_count"]}
Questions asked by teacher: {metrics["teacher_questions_asked"]}
Open-ended questions asked: {metrics["teacher_open_questions"]}
Teacher speech rate: {metrics["teacher_wpm"]} Words Per Minute (WPM)
Teacher filler words used: {metrics["teacher_filler_count"]}
Unique students who spoke: {metrics["unique_students_engaged"]}/6
Students never addressed: {', '.join(metrics["students_never_addressed"]) or 'None — great!'}
Students addressed by teacher: {', '.join(metrics["students_addressed_by_teacher"]) or 'None'}
Events triggered: {metrics["events_triggered"]}
Avg student attention: {metrics["avg_student_attention"]}%
Avg student confusion: {metrics["avg_student_confusion"]}%
Avg student understanding: {metrics["avg_student_understanding"]}%
Most engaged: {metrics["most_engaged_student"]}
Most confused: {metrics["most_confused_student"]}
Least engaged: {metrics["least_engaged_student"]}

Teacher Adaptability Score: {adaptability_res["score"]}/10 (calculated from real responses to confusion, adjustments to speaking pace, interruption handling, participation encouragement of quiet/shy students, and strategy switches)
Teacher Adaptability Feedback: {adaptability_res["feedback"]}

Simulation Realism Score: {realism_res["score"]}/10 (calculated mathematically from turn diversity shannon entropy, response uniqueness vocabulary ratios, consistency checks, emotional smoothness, and event interaction quality)
Simulation Realism Feedback: {", ".join(realism_res["weaknesses"])}

═══ TRANSCRIPT ═══
{transcript_str}

═══ SCORING RULES ═══
Base your scores on the REAL METRICS above, not on feelings:
- Communication (0-100): Clarity, grade-appropriate language, explanation quality.
  If teacher used complex jargon for primary students, deduct heavily.
- Engagement (0-100): Based on unique_students_engaged and students_addressed.
  {metrics["unique_students_engaged"]}/6 students spoke. {'Students never addressed: ' + ', '.join(metrics["students_never_addressed"]) + ' — deduct for each unengaged student.' if metrics["students_never_addressed"] else 'All students engaged — bonus points!'}
- Time Management (0-100): Teacher speaking was {metrics["teacher_speaking_pct"]}%.
  Ideal is 40-50% teacher, 50-60% student. Penalize if teacher > 70%.
- Question Handling (0-100): Teacher asked {metrics["teacher_questions_asked"]} questions ({metrics["teacher_open_questions"]} open-ended).
  Was the teacher patient with confused students? Did they address the most confused student ({metrics["most_confused_student"]})?

Return ONLY raw JSON:
{{
    "communication_score": integer 0-100,
    "engagement_score": integer 0-100,
    "time_management_score": integer 0-100,
    "question_handling_score": integer 0-100,
    "suggestions": "detailed markdown containing sections: Strengths, Weaknesses, Specific B.Ed Pedagogical Advice, a dedicated '### 🎙️ Teacher Speaking Style Analysis' section detailing Speaking Pace ({metrics["teacher_wpm"]} WPM, ideal 120-150 WPM), Filler Word Usage ({metrics["teacher_filler_count"]} count), and Questioning Technique ({metrics["teacher_open_questions"]} open-ended questions asked), a dedicated '### 🛠️ Teacher Adaptability Analysis' presenting the Adaptability Score ({adaptability_res["score"]}/10) and feedback: {adaptability_res["feedback"]}, and a dedicated '### 🔬 Simulation Realism Report' presenting the Realism Score ({realism_res["score"]}/10) and weaknesses: {', '.join(realism_res['weaknesses'])}",
    "transcript_summary": "2-3 sentence factual summary"
}}"""

        response_content, provider = await _call_llm_cascade(prompt)
        if response_content:
            cleaned = clean_json_response(response_content)
            result = json.loads(cleaned)
            print(f"[Evaluation] ✓ via {provider}")
            return result

    except Exception as e:
        print(f"[Evaluation] LLM cascade error: {e}")

    # ── Rule-based fallback using real metrics ──
    m = metrics

    # Communication: penalize if teacher talks too much
    comm = 75
    if m["teacher_speaking_pct"] < 60:
        comm += 10
    if m["teacher_questions_asked"] > 2:
        comm += 5

    # Engagement: based on unique students
    eng = 40 + m["unique_students_engaged"] * 10

    # Time management
    time_score = 80
    if m["teacher_speaking_pct"] > 75:
        time_score -= 15
    if m["total_turns"] > 6:
        time_score += 5

    # Question handling
    q_score = 60 + min(20, m["teacher_questions_asked"] * 5)
    if "Riya" in m["students_addressed_by_teacher"]:
        q_score += 5
    if "Aarav" in m["students_addressed_by_teacher"]:
        q_score += 5

    # Cap scores
    comm = min(98, max(30, comm))
    eng = min(98, max(30, eng))
    time_score = min(98, max(30, time_score))
    q_score = min(98, max(30, q_score))

    suggestions_parts = [
        f"### Session Analysis\n",
        f"**Teacher speaking time:** {m['teacher_speaking_pct']}% (ideal: 40-50%)",
        f"**Student participation:** {m['unique_students_engaged']}/6 students spoke",
        f"**Questions asked:** {m['teacher_questions_asked']}",
    ]

    if m["students_never_addressed"]:
        suggestions_parts.append(
            f"\n**⚠ Students never engaged:** {', '.join(m['students_never_addressed'])}. "
            "Try calling on these students by name in future sessions."
        )

    if m["avg_student_confusion"] > 40:
        suggestions_parts.append(
            f"\n**⚠ High confusion ({m['avg_student_confusion']}%):** "
            f"Student {m['most_confused_student']} was most confused. "
            "Consider using simpler analogies and checking understanding more frequently."
        )

    suggestions_parts.append(
        f"\n### 🎙️ Teacher Speaking Style Analysis\n"
        f"- **Speaking Pace:** {m['teacher_wpm']} WPM. "
        f"{'This is a good, steady pedagogical pace (ideal: 120-150 WPM).' if 120 <= m['teacher_wpm'] <= 150 else ('Your pace is slightly fast (>150 WPM). Try to slow down for better student absorption.' if m['teacher_wpm'] > 150 else 'Your pace is a bit slow (<120 WPM). Injecting more energy can keep the classroom engaged.')}\n"
        f"- **Filler Word Usage:** {m['teacher_filler_count']} filler words detected. "
        f"{'Excellent, you spoke very deliberately!' if m['teacher_filler_count'] <= 2 else 'Try to pause deliberately instead of using filler words (um, uh, like).'}\n"
        f"- **Questioning Technique:** {m['teacher_open_questions']} open-ended questions asked out of {m['teacher_questions_asked']} total questions. "
        f"{'Great job using open-ended questions to stimulate critical thinking!' if m['teacher_open_questions'] > 1 else 'Try asking more open-ended questions (starting with \"Why\" or \"How\") to engage students deeper.'}"
    )

    suggestions_parts.append(
        f"\n### 🛠️ Teacher Adaptability Analysis\n"
        f"- **Adaptability Score:** {adaptability_res['score']}/10\n"
        f"- **Feedback:** {adaptability_res['feedback']}"
    )

    suggestions_parts.append(
        f"\n### 🔬 Simulation Realism Report\n"
        f"- **Realism Score:** {realism_res['score']}/10\n"
        f"- **Weaknesses Checked:**\n" + "\n".join(f"  - {w}" for w in realism_res["weaknesses"])
    )

    suggestions_parts.append(
        "\n**Recommendation:** Aim for 40% teacher talk, 60% student interaction. "
        "Address each student by name at least once per session."
    )

    return {
        "communication_score": int(comm),
        "engagement_score": int(eng),
        "time_management_score": int(time_score),
        "question_handling_score": int(q_score),
        "suggestions": "\n".join(suggestions_parts),
        "transcript_summary": (
            f"Session on {subject} ({topic}) for {class_level}. "
            f"{m['teacher_turns']} teacher turns, {m['student_turns']} student responses, "
            f"{m['unique_students_engaged']}/6 students engaged."
        ),
    }
