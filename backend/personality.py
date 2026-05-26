"""
Independent Personality Engine for Future Classroom Simulator.

Each student has a unique personality profile with:
- Trait scores (curiosity, confidence, attention, etc.)
- Speech patterns (how they talk)
- Behavior rules (how they react to different situations)
- Grade-level adaptations (how they speak at different age levels)
- Response probability calculator
- Classroom state manager
"""

import os
import random
import json
from typing import Dict, Any, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# STUDENT PERSONALITY PROFILES
# ──────────────────────────────────────────────────────────────────────────────

STUDENT_PERSONALITIES: Dict[str, Dict[str, Any]] = {
    "Aarav": {
        "role": "Curious student",
        "traits": {
            "curiosity": 95,
            "confidence": 80,
            "attention_base": 90,
            "confusion_base": 15,
            "interrupt_probability": 25,
            "silence_probability": 5,
            "volunteer_probability": 70,
            "distraction_probability": 8,
        },
        "speech_patterns": [
            "starts questions with 'But wait...' or 'How does...' or 'What if...'",
            "connects topics to things he read in books or saw on YouTube",
            "uses 'actually' and 'I was thinking...' often",
            "asks follow-up questions that go deeper than what was taught",
            "never uses academic jargon — talks like a genuinely curious kid",
        ],
        "behavior_rules": [
            "If teacher explains something → asks a deeper 'why' or 'how' question",
            "If teacher asks a question → tries to answer with enthusiasm + adds a follow-up",
            "If another student is wrong → politely says 'I think it might be different...'",
            "If confused → asks for clarification with genuine curiosity, not frustration",
            "If teacher praises → gets excited and asks an even harder question",
        ],
        "grade_adaptation": {
            "primary": "Uses simple words like 'cool', 'wow', 'why does that happen?', compares to toys/cartoons/animals",
            "middle": "Connects to science experiments, YouTube videos, video games, uses pre-teen vocabulary",
            "high": "References real-world applications, current events, asks about edge cases and exceptions",
        },
    },
    "Ananya": {
        "role": "Shy student",
        "traits": {
            "curiosity": 45,
            "confidence": 20,
            "attention_base": 75,
            "confusion_base": 35,
            "interrupt_probability": 2,
            "silence_probability": 60,
            "volunteer_probability": 8,
            "distraction_probability": 15,
        },
        "speech_patterns": [
            "starts with 'um...' or '...' pauses",
            "trails off mid-sentence with '...I think?' or '...maybe?'",
            "speaks in fragments, not full sentences",
            "voice gets quieter toward end of sentences",
            "often just nods or says a single word",
        ],
        "behavior_rules": [
            "If teacher calls her by name → gives a short nervous answer, often correct but uncertain",
            "If teacher asks the general class → stays completely silent",
            "If she knows the answer → still hesitates and second-guesses herself",
            "If praised → shows slight relief, whispers 'thank you...' or just nods",
            "If confused → says nothing, looks down, does NOT ask for help",
            "If another student explains clearly → quietly nods in understanding",
        ],
        "grade_adaptation": {
            "primary": "Almost inaudible, might just nod or say one word like 'yes' or 'okay'",
            "middle": "Short fragmented sentences, always uncertain, adds 'sorry' unnecessarily",
            "high": "Can form thoughts but hedges everything with 'maybe', 'I think', 'I'm not sure but...'",
        },
    },
    "Vihaan": {
        "role": "Distracted student",
        "traits": {
            "curiosity": 30,
            "confidence": 55,
            "attention_base": 35,
            "confusion_base": 30,
            "interrupt_probability": 15,
            "silence_probability": 40,
            "volunteer_probability": 10,
            "distraction_probability": 75,
        },
        "speech_patterns": [
            "starts with 'Wait, what?' or 'Huh?' or 'Sorry, I wasn't listening...'",
            "mentions completely unrelated things — lunch, birds outside, his pencil, recess",
            "asks 'What page are we on?' or 'Did you already explain this?'",
            "suddenly tunes in when something catches his interest (experiments, games, food analogies)",
        ],
        "behavior_rules": [
            "If teacher calls him directly → snaps to attention, says 'Sorry, what was the question?'",
            "If teacher explains for more than 2 turns → zones out, mentions random thing",
            "If topic relates to something fun (experiments, games, sports) → suddenly interested and engaged",
            "If scolded → pretends to pay attention for 1-2 turns, then drifts again",
            "If asked a question he wasn't paying attention to → guesses wildly or says 'I don't know, sorry'",
        ],
        "grade_adaptation": {
            "primary": "Plays with eraser, looks at ceiling, mentions recess and lunch constantly",
            "middle": "Doodles in notebook, thinks about video games, occasionally contributes when interested",
            "high": "Scrolls through notes but isn't reading, daydreams, checks the clock",
        },
    },
    "Ishaan": {
        "role": "Hyperactive student",
        "traits": {
            "curiosity": 85,
            "confidence": 90,
            "attention_base": 70,
            "confusion_base": 20,
            "interrupt_probability": 80,
            "silence_probability": 3,
            "volunteer_probability": 95,
            "distraction_probability": 10,
        },
        "speech_patterns": [
            "uses excited energy: 'OH! OH! I KNOW!' and 'PICK ME! PICK ME!'",
            "speaks in excited bursts with exclamation marks!!",
            "jumps between ideas without finishing the previous one",
            "suggests wild experiments or activities for everything",
            "uses 'Can we try...?!' and 'What if we...?!' constantly",
        ],
        "behavior_rules": [
            "If teacher asks any question → immediately blurts out answer (often partially right, sometimes completely wrong)",
            "If teacher is explaining → interrupts with 'Can we do an experiment?!' or 'I have an idea!'",
            "If told to wait → can only hold for 1 turn before speaking again",
            "If another student answers → says 'I was going to say that!' or adds his own spin",
            "If praised → gets even MORE excited and energetic",
            "If ignored → gets restless, fidgets, makes noises",
        ],
        "grade_adaptation": {
            "primary": "Bounces in seat, can't sit still, makes sound effects, wants to touch/build everything",
            "middle": "Suggests wild experiments, connects everything to YouTube videos and TikToks",
            "high": "Enthusiastic but slightly more channeled, proposes ambitious projects and debates",
        },
    },
    "Riya": {
        "role": "Weak learner",
        "traits": {
            "curiosity": 40,
            "confidence": 30,
            "attention_base": 65,
            "confusion_base": 55,
            "interrupt_probability": 5,
            "silence_probability": 35,
            "volunteer_probability": 12,
            "distraction_probability": 20,
        },
        "speech_patterns": [
            "says 'I don't get it...' and 'Can you explain again?' frequently",
            "mixes up terminology consistently",
            "uses very simple words, avoids any technical term",
            "often says 'Is that right?' seeking validation",
            "compares complex ideas to very basic everyday things",
        ],
        "behavior_rules": [
            "If teacher uses complex vocabulary → asks 'What does that word mean?'",
            "If teacher explains simply with an analogy → shows understanding: 'Oh! Like [simple thing]?'",
            "If teacher moves too fast → stays confused silently until directly called on",
            "If praised for a correct answer → confidence temporarily boosts, smiles",
            "If another student explains clearly in simple words → says 'Oh, that makes more sense!'",
            "If given a visual/diagram → understands better than verbal explanation",
        ],
        "grade_adaptation": {
            "primary": "Struggles with basic concepts, needs physical/visual examples, counts on fingers",
            "middle": "Can follow simple one-step explanations but gets lost on multi-step reasoning",
            "high": "Understands basics but can't connect them to form deeper insights, needs scaffolding",
        },
    },
    "Kabir": {
        "role": "Overconfident student",
        "traits": {
            "curiosity": 60,
            "confidence": 95,
            "attention_base": 70,
            "confusion_base": 10,
            "interrupt_probability": 55,
            "silence_probability": 5,
            "volunteer_probability": 85,
            "distraction_probability": 12,
        },
        "speech_patterns": [
            "says 'Pfft, that's easy!' and 'Obviously...' and 'Everyone knows that'",
            "uses 'I already knew this' and 'My dad/brother told me about this'",
            "gives confident wrong answers with zero doubt",
            "slightly sassy and cocky tone",
            "dismisses other students' answers: 'No no no, that's not right...'",
        ],
        "behavior_rules": [
            "If teacher asks a question → answers immediately and very confidently (often wrong or half-right)",
            "If corrected → says 'Yeah, that's what I meant' or 'I was about to say that'",
            "If another student gets praised → slightly annoyed, tries to one-up them",
            "If something is actually hard → still pretends to know it, bluffs",
            "If genuinely learns something new → says 'Yeah, I guess that's a different way to look at it'",
            "If asked to explain his reasoning → gets a bit flustered but doubles down",
        ],
        "grade_adaptation": {
            "primary": "'I already know this, my dad told me!' — brags about knowing things from home",
            "middle": "Uses big words incorrectly to sound smart, name-drops concepts he half-understands",
            "high": "Gives half-right answers with absolute confidence, good at sounding knowledgeable",
        },
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# CLASSROOM STATE MANAGER
# ──────────────────────────────────────────────────────────────────────────────

def compute_classroom_state(
    turn_number: int,
    session_duration_minutes: int,
    student_states: list,
    noise: float = 30.0,
    stress: float = 20.0,
) -> Dict[str, Any]:
    """
    Computes aggregate classroom metrics that evolve over time.
    Students' behaviors change based on these metrics.
    """
    import json
    # Estimate roughly 2 turns per minute
    estimated_total_turns = max(1, session_duration_minutes * 2)
    elapsed_ratio = min(1.0, turn_number / estimated_total_turns)

    # Attention naturally decays over time (lecture fatigue)
    attention_decay = min(35, int(elapsed_ratio * 45))

    if student_states:
        avg_attention = sum(s.attention_level for s in student_states) / len(student_states)
        avg_confusion = sum(s.confusion_level for s in student_states) / len(student_states)
        avg_confidence = sum(s.confidence_level for s in student_states) / len(student_states)
        avg_understanding = sum(s.understanding_level for s in student_states) / len(student_states)
        avg_curiosity = sum(getattr(s, "curiosity_level", 50) for s in student_states) / len(student_states)
        
        # Calculate average stress from student memory if available, else fallback
        student_stresses = []
        for s in student_states:
            try:
                mem = get_student_memory(s)
                student_stresses.append(mem.get("dynamic_state", {}).get("stress", s.confusion_level * 0.7))
            except Exception:
                student_stresses.append(s.confusion_level * 0.7)
        avg_stress = sum(student_stresses) / len(student_states)
    else:
        avg_attention = 75
        avg_confusion = 25
        avg_confidence = 65
        avg_understanding = 70
        avg_curiosity = 55
        avg_stress = 20

    effective_attention = max(10, avg_attention - attention_decay)

    # Base target energy decays over time, but is boosted by student curiosity
    target_energy = max(10.0, min(100.0, 90.0 - (elapsed_ratio * 50.0) + (avg_curiosity * 0.15)))

    # Fetch previous state checkpoint to apply momentum evolution
    prev_energy = 80.0
    prev_engagement = 70.0
    
    # Locate DB session from student state objects using object_session
    if student_states:
        try:
            from sqlalchemy.orm import object_session
            db = object_session(student_states[0])
            if db:
                from models import SessionMessage
                session_id = student_states[0].session_id
                last_checkpoint = db.query(SessionMessage).filter(
                    SessionMessage.session_id == session_id,
                    SessionMessage.sender_type == "state_checkpoint"
                ).order_by(SessionMessage.timestamp.desc()).first()
                if last_checkpoint:
                    chk = json.loads(last_checkpoint.message_text)
                    prev_energy = chk.get("energy", 80.0)
                    prev_engagement = chk.get("engagement", 70.0)
        except Exception as db_err:
            print(f"[ECE] Database fetch previous state warning: {db_err}")

    # Momentum-based evolution of energy (0.8 old + 0.2 new)
    base_energy = round(prev_energy * 0.8 + target_energy * 0.2, 1)

    # Determine energy level text
    if base_energy > 70:
        energy_level = "high"
    elif base_energy > 40:
        energy_level = "medium"
    else:
        energy_level = "low"

    effective_attention = round(effective_attention, 1)
    avg_confusion = round(avg_confusion, 1)
    avg_confidence = round(avg_confidence, 1)
    avg_understanding = round(avg_understanding, 1)
    avg_curiosity = round(avg_curiosity, 1)
    avg_stress = round(max(0.0, min(100.0, stress or avg_stress)), 1)
    effective_noise = round(max(0.0, min(100.0, noise)), 1)
    
    # Participation rate (percentage of speaking count over turns)
    total_speaks = sum(s.participation_count for s in student_states) if student_states else 0
    participation = round(min(100.0, (total_speaks / max(1, turn_number)) * 100.0), 1)

    # Engagement calculation: (Attention + Confidence + Understanding - Confusion + base_energy - avg_stress) / 2.5
    target_engagement = max(0.0, min(100.0, (effective_attention + avg_confidence + avg_understanding - avg_confusion + base_energy - avg_stress) / 2.5))
    
    # Apply momentum to engagement (0.8 old + 0.2 new)
    engagement = round(prev_engagement * 0.8 + target_engagement * 0.2, 1)

    # Reconcile classroom state values using the validation engine to resolve impossible states
    from validation import SimulationValidationEngine
    engagement = SimulationValidationEngine.reconcile_classroom_state(
        attention=effective_attention,
        engagement=engagement,
        confusion=avg_confusion
    )

    return {
        "turn_number": turn_number,
        "elapsed_ratio": round(elapsed_ratio, 2),
        "attention_decay": attention_decay,
        "attention": effective_attention,
        "confusion": avg_confusion,
        "confidence": avg_confidence,
        "understanding": avg_understanding,
        "curiosity": avg_curiosity,
        "stress": avg_stress,
        "noise": effective_noise,
        "participation": participation,
        "energy": base_energy,
        "engagement": engagement,
        # Backwards compatibility keys
        "avg_class_attention": effective_attention,
        "avg_class_confusion": avg_confusion,
        "avg_class_confidence": avg_confidence,
        "avg_class_understanding": avg_understanding,
        "energy_level": energy_level,
        "needs_activity_change": effective_attention < 50 or avg_confusion > 55,
    }


# Student relationship influence matrix for conversational realism
STUDENT_RELATIONSHIPS = {
    "aarav": {"inspires": ["ananya", "riya"], "reason": "Aarav's deep curiosity inspires other students to pay attention."},
    "kabir": {"influences": ["vihaan"], "reason": "Kabir likes to show off, and Vihaan easily copies his distracted behavior."},
    "ananya": {"follows": ["riya"], "reason": "Ananya quietly nods in agreement when Riya explains or speaks."}
}


def should_student_respond(
    student_name: str,
    personality: Dict[str, Any],
    student_state: Any,
    classroom_state: Dict[str, Any],
    was_addressed: bool,
    is_question: bool,
    conversation_history: List[Dict[str, str]] = None,
) -> float:
    """
    Returns probability (0.0–1.0) that this student should respond this turn.
    ECE Emergent: Driven by dynamic student state variables (stress, attention, confidence, confusion)
    and evolved student relationship matrix coefficients.
    """
    if was_addressed:
        return 0.95  # Almost always responds when directly called on

    # Get student memory for dynamic state/relationships
    memory = get_student_memory(student_state)
    ds = memory.get("dynamic_state", {})
    relationships = memory.get("relationships", {})

    traits = personality["traits"]
    base = (traits["volunteer_probability"] / 100.0)

    # ──── 1. DYNAMIC INDIVIDUAL STATE RULE COUPLING ────
    
    # Stress check: High stress (>60) causes students to avoid volunteering/shut down
    stress = ds.get("stress", 15.0)
    if stress > 60.0:
        base *= 0.35
    
    # Confidence check: Low confidence (<35) reduces volunteering probability
    conf = student_state.confidence_level
    if conf < 35.0:
        base *= 0.45
    elif conf > 80.0:
        base *= 1.25

    # Confusion checks: High confusion (>60) drives students to ask clarification questions if a question is asked,
    # or withdraw completely if not.
    confus = student_state.confusion_level
    if confus > 60.0:
        if is_question:
            base *= 1.6  # High confusion volunteer spike to ask clarifying question
        else:
            base *= 0.4  # Withdraw into silence

    # Attention factor: Low attention (<35) results in a zone-out distraction drop
    att = student_state.attention_level
    if att < 35.0:
        base *= 0.3

    # Classroom energy affects willingness to speak
    energy = classroom_state.get("energy", 50.0)
    if energy < 40.0:
        base *= 0.6
    elif energy > 75.0:
        base *= 1.15

    # Hyperactive students volunteer MORE as class goes on (they get restless)
    if traits["interrupt_probability"] > 50:
        base *= (1.0 + classroom_state["elapsed_ratio"] * 0.3)

    # Shy students volunteer LESS as class goes on (they withdraw further)
    if traits["silence_probability"] > 40:
        base *= (1.0 - classroom_state["elapsed_ratio"] * 0.4)

    # Students who've spoken a lot recently become slightly less likely (fatigue)
    if student_state.participation_count > 4:
        base *= 0.8

    # ──── 2. RESPONSE FATIGUE DECAY SYSTEM ────
    fatigue_factor = 1.0
    if conversation_history:
        student_msgs = [m for m in conversation_history if m.get("sender_type") == "student"]
        if student_msgs:
            last_student_sender = student_msgs[-1].get("sender_name", "").lower()
            if last_student_sender == student_name.lower():
                fatigue_factor = 0.0  # Prevent volunteering consecutively to ensure diverse student participation
            
    base *= fatigue_factor

    # ──── 3. EVOLVED RELATIONSHIP MUTATORS ────
    if conversation_history:
        valid_history = [m for m in conversation_history if m.get("sender_type") != "system"]
        if valid_history:
            last_msg = valid_history[-1]
            last_sender = last_msg.get("sender_name", "").lower()
            
            # Find if there is an active relationship entry in our evolved memory mappings
            matched_key = None
            for key in relationships.keys():
                if key.lower().strip() == last_sender:
                    matched_key = key
                    break
            
            if matched_key:
                rel_info = relationships[matched_key]
                if isinstance(rel_info, dict) and "trust" in rel_info:
                    trust = rel_info.get("trust", 50.0)
                    friendship = rel_info.get("friendship", 50.0)
                    annoyance = rel_info.get("annoyance", 10.0)
                    influence = rel_info.get("influence", 30.0)
                    supportiveness = rel_info.get("supportiveness", 50.0)
                    
                    # Positive relationship factors increase likelihood
                    base *= (0.7 + (friendship / 100.0) * 0.4 + (influence / 100.0) * 0.2)
                    
                    # Annoyance factor mutates response probabilities
                    if annoyance > 45.0:
                        if student_name.lower() in ["aarav", "kabir", "ishaan"]:
                            base *= 1.35  # Assertive/curious students interrupt to correct
                        else:
                            base *= 0.45  # Quiet/shy students withdraw
                else:
                    strength = rel_info.get("strength", 1.0) if isinstance(rel_info, dict) else 1.0
                    base *= strength

    # ──── 4. GLOBAL MOOD ATAVISMS ────
    class_attention = classroom_state.get("attention", 75.0)
    class_confusion = classroom_state.get("confusion", 25.0)

    # Low Attention Adapters (< 50)
    if class_attention < 50.0:
        if student_name.lower() == "vihaan":   # Vihaan zones out entirely
            base *= 0.2
        elif student_name.lower() == "kabir":  # Kabir gets restless, volunteers more
            base *= 1.4

    # High Confusion Adapters (> 55)
    if class_confusion > 55.0:
        if student_name.lower() == "riya":     # Riya volunteers more to ask confused questions
            base *= 1.5
        elif student_name.lower() == "ananya": # Ananya gets timid, volunteers even less
            base *= 0.1

    # ──── 5. SIMULATION VALIDATION ENGINE CODES ────
    ds = memory.get("dynamic_state", {})
    
    # Interruption penalty reduces base response volunteering rate
    if ds.get("interruption_penalty_turns", 0) > 0:
        base = min(0.10, base * 0.5)
        
    # Silence timeout boost
    if ds.get("turns_since_spoken", 0) >= 15:
        base = max(1.0, base * 2.0)

    return min(0.95, max(0.02, base))


def select_responders(
    teacher_message: str,
    addressed_student: Optional[str],
    student_states: list,
    classroom_state: Dict[str, Any],
    students_info: list,
    conversation_history: List[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Selects 1-2 students who should respond this turn based on personality probabilities.
    Enables interruptions, follow-ups, and realistic classroom dynamics.
    Adapts interrupt probability dynamically based on low class attention and relationships.
    """
    responders = []
    is_question = teacher_message.strip().endswith("?") or any(
        w in teacher_message.lower()
        for w in ["what", "why", "how", "who", "when", "which", "explain",
                   "tell me", "can you", "do you", "does", "क्या", "क्यों",
                   "कैसे", "কেন", "কী", "কীভাবে"]
    )

    # Build a lookup from student name to state
    state_map = {s.student_name: s for s in student_states}

    # 1. If a student is directly addressed, they respond first
    if addressed_student:
        responders.append({
            "name": addressed_student,
            "reason": "addressed",
            "info": next((s for s in students_info if s["name"].lower() == addressed_student.lower()), students_info[0]),
        })

    # 2. Check if teacher mentioned a student name
    input_lower = teacher_message.lower()
    for s_info in students_info:
        if s_info["name"].lower() in input_lower and s_info["name"] not in [r["name"] for r in responders]:
            responders.append({
                "name": s_info["name"],
                "reason": "mentioned",
                "info": s_info,
            })

    # 3. Calculate response probability for each remaining student
    candidates = []
    for s_info in students_info:
        name = s_info["name"]
        if name in [r["name"] for r in responders]:
            continue
        state = state_map.get(name)
        if not state:
            continue
        personality = STUDENT_PERSONALITIES.get(name, {})
        if not personality:
            continue

        prob = should_student_respond(
            name, personality, state, classroom_state,
            was_addressed=False, is_question=is_question,
            conversation_history=conversation_history
        )
        candidates.append((name, prob, personality, s_info))

    # 4. Roll dice for each candidate
    class_attention = classroom_state.get("attention", 75.0)
    
    # Get last valid sender for relationships
    last_sender = ""
    if conversation_history:
        valid_h = [m for m in conversation_history if m.get("sender_type") != "system"]
        if valid_h:
            last_sender = valid_h[-1].get("sender_name", "").lower()

    for name, prob, personality, s_info in candidates:
        if random.random() < prob:
            traits = personality["traits"]
            
            # Get dynamic state to check for interruption penalty
            state_rec = state_map.get(name)
            ds = {}
            if state_rec and state_rec.memory_json:
                try:
                    import json as _json
                    ds = _json.loads(state_rec.memory_json).get("dynamic_state", {})
                except Exception:
                    pass
            
            # Dynamic interrupt probability scale for Low Class Attention
            interrupt_prob = traits["interrupt_probability"]
            if class_attention < 50.0 and name.lower() == "kabir":
                interrupt_prob = min(95.0, interrupt_prob * 1.5)  # Kabir interrupts significantly more
            
            # Relationship influence: Kabir encourages Vihaan to interrupt/side-chatter
            if last_sender == "kabir" and name.lower() == "vihaan":
                interrupt_prob = min(90.0, interrupt_prob * 1.8)
                
            # Apply interruption penalty if active
            if ds.get("interruption_penalty_turns", 0) > 0:
                interrupt_prob *= 0.5
                
            is_interrupt = random.random() < (interrupt_prob / 100.0)
            responders.append({
                "name": name,
                "reason": "interrupt" if is_interrupt else "volunteer",
                "info": s_info,
            })

    # 5. Ensure at least 1 responder
    if not responders:
        # Pick the most likely candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        if candidates:
            responders.append({
                "name": candidates[0][0],
                "reason": "default",
                "info": candidates[0][3],
            })
        elif students_info:
            responders.append({
                "name": students_info[0]["name"],
                "reason": "default",
                "info": students_info[0],
            })

    # 6. Cap at 2 responders per turn
    return responders[:2]


# ──────────────────────────────────────────────────────────────────────────────
# ATTENTION DECAY — Apply per turn
# ──────────────────────────────────────────────────────────────────────────────

def apply_attention_decay(student_states: list, turn_number: int, db) -> None:
    """
    Applies natural attention decay to all students each turn.
    Different personalities decay at different rates.
    """
    for state in student_states:
        personality = STUDENT_PERSONALITIES.get(state.student_name, {})
        if not personality:
            continue

        traits = personality["traits"]

        # Base decay per turn (1-4 points depending on personality)
        if traits["attention_base"] > 80:
            decay = random.randint(0, 2)  # Focused students decay slowly
        elif traits["attention_base"] > 50:
            decay = random.randint(1, 3)  # Medium students
        else:
            decay = random.randint(2, 5)  # Distracted students decay fast

        # Distracted students have random attention spikes (they tune in/out)
        if traits.get("distraction_probability", 0) > 50:
            if random.random() < 0.2:  # 20% chance to suddenly tune in
                decay = -random.randint(5, 15)  # Attention boost

        state.attention_level = max(5, min(100, state.attention_level - decay))

        # Confusion slowly builds if attention is low
        if state.attention_level < 40:
            confusion_gain = random.randint(1, 3)
            state.confusion_level = min(100, state.confusion_level + confusion_gain)

    db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# STRUCTURED MEMORY HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _get_initial_long_term(student_name: str) -> Dict[str, Any]:
    """Retrieves standard pre-configured long-term learning history and subject profiles."""
    name_lower = student_name.lower().strip()
    
    profiles = {
        "aarav": {
            "subject_strengths": ["Physics", "Practical experiments", "Space science"],
            "subject_weaknesses": ["Abstract history", "Rote memorization", "Grammar rules"],
            "learning_history": ["Solar system basics", "Simple chemical reactions"],
            "participation_patterns": {"total_speaks": 15, "interrupt_count": 2, "questions_asked": 8}
        },
        "ananya": {
            "subject_strengths": ["Fine arts", "Creative writing", "Literature"],
            "subject_weaknesses": ["Mental math", "Algebra", "Public speaking"],
            "learning_history": ["Poetry structures", "Indian national movement summary"],
            "participation_patterns": {"total_speaks": 2, "interrupt_count": 0, "questions_asked": 0}
        },
        "vihaan": {
            "subject_strengths": ["Sports trivia", "General knowledge", "Visual geometry"],
            "subject_weaknesses": ["Long lectures", "Algebra formulas", "Spellings"],
            "learning_history": ["Simple machine concepts"],
            "participation_patterns": {"total_speaks": 4, "interrupt_count": 1, "questions_asked": 1}
        },
        "ishaan": {
            "subject_strengths": ["Robotics", "Hands-on projects", "Kinetic science"],
            "subject_weaknesses": ["Calculations in seat", "Silent reading", "Grammar rules"],
            "learning_history": ["Friction and force basics"],
            "participation_patterns": {"total_speaks": 22, "interrupt_count": 14, "questions_asked": 12}
        },
        "riya": {
            "subject_strengths": ["Social sciences", "Environmental studies", "Moral education"],
            "subject_weaknesses": ["Abstract physics", "Double-digit division", "Chemical equations"],
            "learning_history": ["Water cycle basics", "Types of soils"],
            "participation_patterns": {"total_speaks": 6, "interrupt_count": 0, "questions_asked": 3}
        },
        "kabir": {
            "subject_strengths": ["Logic puzzles", "Competitive math", "Debates"],
            "subject_weaknesses": ["Critical self-reflection", "Collaborative projects"],
            "learning_history": ["Integers and fractions", "Basic geometry theorems"],
            "participation_patterns": {"total_speaks": 18, "interrupt_count": 8, "questions_asked": 4}
        }
    }
    
    return profiles.get(name_lower, profiles["aarav"])


# Seating Subgroups & Social Friendship Circles for Contagion Diffusion
CLASSROOM_SUBGROUPS = {
    "front_bench": ["Aarav", "Ananya"],
    "quiet": ["Ananya", "Riya"],
    "distracted": ["Vihaan", "Ishaan"],
    "active_learners": ["Aarav", "Kabir"]
}

FRIEND_CIRCLES = [
    ["Vihaan", "Kabir", "Ishaan"], # Back-bench/distracted circle
    ["Aarav", "Ananya", "Riya"]   # Studious/shy circle
]

def migrate_relationship(rel_data: Any) -> Dict[str, float]:
    """Helper to upgrade legacy relationship data schemas to multi-dimensional dynamic values on the fly."""
    # Default values
    trust = 50.0
    friendship = 50.0
    annoyance = 10.0
    influence = 30.0
    supportiveness = 50.0

    if isinstance(rel_data, dict):
        if "trust" in rel_data and "friendship" in rel_data:
            return {
                "trust": float(rel_data.get("trust", 50.0)),
                "friendship": float(rel_data.get("friendship", 50.0)),
                "annoyance": float(rel_data.get("annoyance", 10.0)),
                "influence": float(rel_data.get("influence", 30.0)),
                "supportiveness": float(rel_data.get("supportiveness", 50.0))
            }
        
        # Upgrade legacy type & strength
        rel_type = rel_data.get("type", "neutral")
        strength = float(rel_data.get("strength", 1.0))
        
        if rel_type == "inspires":
            trust = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 80.0))
            friendship = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 30.0))
            influence = min(100.0, max(0.0, 30.0 + (strength - 1.0) * 80.0))
            supportiveness = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 50.0))
        elif rel_type == "influences":
            trust = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 40.0))
            friendship = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 70.0))
            influence = min(100.0, max(0.0, 30.0 + (strength - 1.0) * 90.0))
            supportiveness = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 40.0))
        elif rel_type == "follows":
            trust = min(100.0, max(0.0, 55.0 + (strength - 1.0) * 60.0))
            friendship = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 40.0))
            influence = min(100.0, max(0.0, 30.0 + (strength - 1.0) * 70.0))
            supportiveness = min(100.0, max(0.0, 50.0 + (strength - 1.0) * 40.0))

    return {
        "trust": round(trust, 1),
        "friendship": round(friendship, 1),
        "annoyance": round(annoyance, 1),
        "influence": round(influence, 1),
        "supportiveness": round(supportiveness, 1)
    }

def _get_initial_relationships(student_name: str) -> Dict[str, Any]:
    name_lower = student_name.lower().strip()
    if name_lower == "aarav":
        return {
            "Ananya": {"trust": 75.0, "friendship": 60.0, "annoyance": 10.0, "influence": 55.0, "supportiveness": 65.0},
            "Riya": {"trust": 75.0, "friendship": 60.0, "annoyance": 10.0, "influence": 55.0, "supportiveness": 65.0}
        }
    elif name_lower == "kabir":
        return {
            "Vihaan": {"trust": 60.0, "friendship": 80.0, "annoyance": 10.0, "influence": 85.0, "supportiveness": 70.0},
            "Ishaan": {"trust": 50.0, "friendship": 60.0, "annoyance": 40.0, "influence": 40.0, "supportiveness": 40.0}
        }
    elif name_lower == "ananya":
        return {
            "Riya": {"trust": 85.0, "friendship": 70.0, "annoyance": 10.0, "influence": 80.0, "supportiveness": 70.0},
            "Aarav": {"trust": 70.0, "friendship": 50.0, "annoyance": 15.0, "influence": 50.0, "supportiveness": 60.0}
        }
    elif name_lower == "vihaan":
        return {
            "Kabir": {"trust": 70.0, "friendship": 85.0, "annoyance": 10.0, "influence": 85.0, "supportiveness": 60.0},
            "Ishaan": {"trust": 65.0, "friendship": 80.0, "annoyance": 15.0, "influence": 75.0, "supportiveness": 60.0}
        }
    elif name_lower == "ishaan":
        return {
            "Vihaan": {"trust": 60.0, "friendship": 80.0, "annoyance": 20.0, "influence": 75.0, "supportiveness": 65.0},
            "Kabir": {"trust": 55.0, "friendship": 70.0, "annoyance": 30.0, "influence": 60.0, "supportiveness": 50.0}
        }
    elif name_lower == "riya":
        return {
            "Ananya": {"trust": 80.0, "friendship": 75.0, "annoyance": 10.0, "influence": 65.0, "supportiveness": 75.0},
            "Aarav": {"trust": 85.0, "friendship": 65.0, "annoyance": 10.0, "influence": 70.0, "supportiveness": 80.0}
        }
    return {}

def get_student_memory(state) -> Dict[str, Any]:
    """Parse the structured memory JSON from a StudentState record supporting ECE dynamic state & relationships."""
    data = {
        "short_term": {
            "concepts_taught": [],
            "questions_asked_by_student": [],
            "questions_received_from_teacher": [],
            "key_interactions": [],
            "last_responses": [],
            "current_confusion": 20
        },
        "long_term": _get_initial_long_term(state.student_name),
        "dynamic_state": {
            "stress": 15.0,
            "social_influence": 1.0,
            "participation_rate": 0.0,
            "mood": "normal"
        },
        "relationships": _get_initial_relationships(state.student_name)
    }

    if state.memory_json:
        try:
            parsed = json.loads(state.memory_json)
            if isinstance(parsed, dict):
                # Migrate or populate tiers
                if "short_term" in parsed:
                    data["short_term"].update(parsed["short_term"])
                else:
                    # Upgrade legacy dictionary to short_term
                    for k in ["concepts_taught", "questions_asked_by_student", "questions_received_from_teacher", "key_interactions", "last_responses"]:
                        if k in parsed:
                            data["short_term"][k] = parsed[k]

                if "long_term" in parsed:
                    data["long_term"].update(parsed["long_term"])
                
                if "dynamic_state" in parsed:
                    data["dynamic_state"].update(parsed["dynamic_state"])
                else:
                    data["dynamic_state"]["stress"] = float(state.confusion_level or 20) * 0.7

                if "relationships" in parsed:
                    data["relationships"] = parsed["relationships"]
        except Exception:
            pass

    # Ensure all peers are present and migrated to deep schema
    all_peers = ["Aarav", "Ananya", "Vihaan", "Ishaan", "Riya", "Kabir"]
    for peer in all_peers:
        if peer.lower() == state.student_name.lower():
            continue
            
        matched_key = None
        for k in data["relationships"].keys():
            if k.lower() == peer.lower():
                matched_key = k
                break
                
        if matched_key:
            data["relationships"][matched_key] = migrate_relationship(data["relationships"][matched_key])
            # Normalize casing
            if matched_key != peer:
                data["relationships"][peer] = data["relationships"].pop(matched_key)
        else:
            data["relationships"][peer] = {
                "trust": 50.0,
                "friendship": 50.0,
                "annoyance": 10.0,
                "influence": 30.0,
                "supportiveness": 50.0
            }

    return data


def update_student_memory(
    state,
    memory: Dict[str, Any],
    response_text: str,
    teacher_message: str,
    memory_update_text: str,
    turn_number: int,
    is_interrupt: bool = False,
) -> None:
    """Update the structured dual-tier memory after a student responds."""
    # Ensure structured schema is initialized
    if "short_term" not in memory:
        memory = {
            "short_term": memory,
            "long_term": _get_initial_long_term(state.student_name),
            "dynamic_state": {
                "stress": float(state.confusion_level or 20) * 0.7,
                "social_influence": 1.0,
                "participation_rate": 0.0,
                "mood": "normal"
            },
            "relationships": _get_initial_relationships(state.student_name)
        }
        
    st = memory["short_term"]
    lt = memory["long_term"]
    ds = memory.get("dynamic_state", {
        "stress": float(state.confusion_level or 20) * 0.7,
        "social_influence": 1.0,
        "participation_rate": 0.0,
        "mood": "normal"
    })
    
    # Track student interrupts
    if is_interrupt:
        interruption_turns = ds.setdefault("interruption_turns", [])
        interruption_turns.append(turn_number)
        
        # Apply interruption rules/caps immediately
        from validation import SimulationValidationEngine
        ds = SimulationValidationEngine.apply_interruption_rules(state.student_name, turn_number, ds)
    
    # Add this response to last_responses (keep last 5)
    st["last_responses"] = st.get("last_responses", [])
    st["last_responses"].append(response_text)
    st["last_responses"] = st["last_responses"][-5:]

    # Add key interaction summary
    st["key_interactions"] = st.get("key_interactions", [])
    if memory_update_text:
        st["key_interactions"].append(
            f"Turn {turn_number}: {memory_update_text}"
        )
        st["key_interactions"] = st["key_interactions"][-10:]

    # Evolve current confusion levels
    st["current_confusion"] = state.confusion_level or 20

    # Evolve Long-Term participation patterns
    lt["participation_patterns"]["total_speaks"] += 1
    
    # Update dynamic participation rate
    total_speaks = lt["participation_patterns"]["total_speaks"]
    ds["participation_rate"] = round(total_speaks / max(1, turn_number), 2)
    memory["dynamic_state"] = ds
    
    # Serialize back to JSON
    state.memory_json = json.dumps(memory, ensure_ascii=False)


def prune_and_summarize_memory(state) -> None:
    """
    Compresses short-term key interactions into a long-term summarized sentence.
    Prevents prompt context size growth.
    """
    if not state.memory_json:
        return
        
    try:
        memory = json.loads(state.memory_json)
    except Exception:
        return
        
    if not isinstance(memory, dict) or "short_term" not in memory:
        return
        
    st = memory["short_term"]
    lt = memory.get("long_term", {})
    
    key_interactions = st.get("key_interactions", [])
    if len(key_interactions) < 8:
        return
        
    print(f"[MEMORY COMPACTOR] Compacting {len(key_interactions)} key interactions for {state.student_name}...")
    
    # Compile raw questions/interactions text
    raw_text = "; ".join(key_interactions)
    
    summary = ""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            # We can use the Gemini client to generate a quick summary
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = (
                f"You are a classroom session memory compactor. "
                f"Condense the following raw interaction logs of the student {state.student_name} "
                f"into a single short sentence (max 15 words) written in the third person: "
                f"'{raw_text}'. "
                f"Example: '{state.student_name} frequently struggles with fractions but remains active in discussions.'"
            )
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            if response.text:
                summary = response.text.strip().strip('"\'')
        except Exception as e:
            print(f"[MEMORY COMPACTOR] LLM summarization error: {e}")
            
    # Fallback templated summary if LLM key is absent or failed
    if not summary:
        struggled_topics = []
        if any("confused" in item.lower() or "struggle" in item.lower() or "lost" in item.lower() for item in key_interactions):
            struggled_topics.append("struggled with some explanations")
        if any("question" in item.lower() or "asked" in item.lower() for item in key_interactions):
            struggled_topics.append("asked clarifications")
        if any("distracted" in item.lower() or "bored" in item.lower() or "whisper" in item.lower() for item in key_interactions):
            struggled_topics.append("lost focus periodically")
            
        topics_str = " and ".join(struggled_topics) if struggled_topics else "participated in the lesson"
        summary = f"{state.student_name} {topics_str}."
        
    # Append the summary to long-term learning_history
    if "learning_history" not in lt:
        lt["learning_history"] = []
    lt["learning_history"].append(summary)
    
    # Keep learning_history reasonably sized as well (max 5)
    lt["learning_history"] = lt["learning_history"][-5:]
    
    # Empty short-term key_interactions to prevent infinite growth
    st["key_interactions"] = []
    
    # Save back to DB
    memory["short_term"] = st
    memory["long_term"] = lt
    state.memory_json = json.dumps(memory, ensure_ascii=False)


def format_memory_for_prompt(memory: Dict[str, Any]) -> str:
    """Format structured dual-tier memory into a readable string for the AI prompt."""
    st = memory.get("short_term", {})
    lt = memory.get("long_term", {})
    
    parts = []
    
    # 1. Format Long-Term Memory Profile
    if lt:
        parts.append("═══ YOUR LONG-TERM PROFILE & HISTORY ═══")
        parts.append(f"  • Your Subject Strengths: {', '.join(lt.get('subject_strengths', []))}")
        parts.append(f"  • Your Subject Weaknesses: {', '.join(lt.get('subject_weaknesses', []))}")
        parts.append(f"  • Concepts Covered in Past Lessons: {', '.join(lt.get('learning_history', []))}")
        patterns = lt.get("participation_patterns", {})
        parts.append(f"  • General Participation: Total spoken {patterns.get('total_speaks', 0)} times, interrupted {patterns.get('interrupt_count', 0)} times.")
        parts.append("")

    # 2. Format Short-Term Memory Profile
    parts.append("═══ WHAT YOU REMEMBER FROM THIS CURRENT LESSON ═══")
    if st.get("concepts_taught"):
        concepts = st["concepts_taught"][-5:]  # Last 5
        parts.append("  Concepts covered in class so far:")
        for c in concepts:
            status = "✓ understood" if c.get("understood") else "✗ confused"
            parts.append(f"    - {c['concept']} ({status})")

    if st.get("key_interactions"):
        parts.append("  Your recent interactions today:")
        for interaction in st["key_interactions"][-5:]:
            parts.append(f"    - {interaction}")

    if st.get("last_responses"):
        parts.append("  Your last few responses (DO NOT repeat these):")
        for resp in st["last_responses"][-3:]:
            parts.append(f'    - "{resp}"')

    if len(parts) <= 3:
        parts.append("  This is the beginning of the class. No prior interactions yet.")

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# GRADE LEVEL HELPER
# ──────────────────────────────────────────────────────────────────────────────

def get_grade_key(class_level: str) -> str:
    """Convert class_level string to a grade key for personality adaptation."""
    cl = class_level.lower()
    if any(w in cl for w in ["primary", "1-5", "1-3", "4-5", "elementary"]):
        return "primary"
    elif any(w in cl for w in ["middle", "6-8", "6-7", "7-8"]):
        return "middle"
    else:
        return "high"


def evolve_states_and_relationships(
    student_states: List[Any],
    teacher_message: str,
    conversation_history: List[Dict[str, str]],
    db
) -> Dict[str, float]:
    """
    Evolves all student dynamic states and relationship strengths dynamically.
    No hardcoded behaviors. Adjusts noise and stress indicators continuously.
    Returns: {"noise": float, "stress": float}
    """
    import re
    
    # 1. Determine teacher lecture length & features
    words = teacher_message.split()
    word_count = len(words)
    is_question = teacher_message.strip().endswith("?") or any(w in teacher_message.lower() for w in ["what", "why", "how", "who", "explain"])
    
    # Count filler words used by teacher
    fillers = re.findall(r'\b(um|uh|uhm|er|ah|like|actually|you\s+know)\b', teacher_message.lower())
    filler_count = len(fillers)
    
    # Check consecutive teacher lecturing turns
    consecutive_teacher_turns = 0
    for msg in reversed(conversation_history):
        if msg.get("sender_type") == "teacher":
            consecutive_teacher_turns += 1
        else:
            break
            
    # Calculate base class noise and stress adjustments
    turn_noise = 25.0
    turn_stress = 15.0
    
    # Whispering and interruption detection from last student messages
    student_msgs = [m for m in conversation_history if m.get("sender_type") == "student"]
    last_student_msg = student_msgs[-1] if student_msgs else None
    last_student_sender = last_student_msg.get("sender_name", "").lower() if last_student_msg else None
            
    # Adjust global noise based on history
    if last_student_msg:
        text_lower = last_student_msg.get("message_text", "").lower()
        if "experiment" in text_lower or last_student_sender == "ishaan":
            turn_noise += 20.0  # Hyperactive energy increases classroom noise
        elif last_student_sender == "vihaan" and "wait" in text_lower:
            turn_noise += 15.0  # Whispering side chatter
            
    # Adjust stress
    if is_question and len(student_states) > 0:
        turn_stress += 8.0 # Being questioned raises student stress slightly
        
    # Long teacher lectures drain attention and energy, rising stress/noise
    if consecutive_teacher_turns >= 2:
        turn_stress += 5.0 * consecutive_teacher_turns
        turn_noise -= 3.0 * consecutive_teacher_turns # Quiet classroom during lectures, but attention decays
        
    # 2. Pre-calculate direct student deltas
    deltas = {}
    for state in student_states:
        name_lower = state.student_name.lower().strip()
        personality = STUDENT_PERSONALITIES.get(state.student_name, {})
        if not personality:
            continue
            
        attention_delta = 0.0
        confusion_delta = 0.0
        confidence_delta = 0.0
        stress_delta = 0.0
        
        # A. Long lecturing causes attention decay and minor confusion rise
        if consecutive_teacher_turns >= 2:
            base_decay = 4 if personality["traits"]["attention_base"] < 70 else 2
            attention_delta -= base_decay * consecutive_teacher_turns
            confusion_delta += 2.0 * consecutive_teacher_turns
            stress_delta += 3.0
            
        # B. Complex jargon / long sentences increase confusion
        if word_count > 30:
            confusion_delta += 5.0
            stress_delta += 4.0
            
        # C. Teacher using fillers decreases attention
        if filler_count > 1:
            attention_delta -= 3.0 * filler_count
            
        # D. Teacher asking open questions sparks curiosity
        if is_question:
            attention_delta += 8.0 # students alert up!
            confidence_delta -= 2.0 # slight hesitation
            
        # E. Character-specific reactions:
        # Shy students (Ananya) get highly stressed by direct names
        if name_lower == "ananya" and "ananya" in teacher_message.lower():
            stress_delta += 15.0
            confidence_delta -= 5.0
        # Weak learners (Riya) get confused by long lectures
        if name_lower == "riya" and word_count > 25:
            confusion_delta += 10.0
            confidence_delta -= 5.0
        # Hyperactive (Ishaan) gets bored/restless during lectures
        if name_lower == "ishaan" and consecutive_teacher_turns >= 2:
            attention_delta -= 12.0
            
        deltas[state.student_name] = {
            "attention": attention_delta,
            "confusion": confusion_delta,
            "confidence": confidence_delta,
            "stress": stress_delta
        }

    # Initialize diffused deltas with direct deltas
    diffused_deltas = {
        s.student_name: {
            "attention": deltas.get(s.student_name, {}).get("attention", 0.0),
            "confusion": deltas.get(s.student_name, {}).get("confusion", 0.0),
            "confidence": deltas.get(s.student_name, {}).get("confidence", 0.0),
            "stress": deltas.get(s.student_name, {}).get("stress", 0.0)
        }
        for s in student_states
    }

    # Apply social contagion (diffusion)
    for student_name in deltas:
        # Subgroup zone influence
        for group_name, members in CLASSROOM_SUBGROUPS.items():
            if student_name in members:
                for peer in members:
                    if peer != student_name and peer in diffused_deltas:
                        diffused_deltas[peer]["attention"] += deltas[student_name]["attention"] * 0.35
                        diffused_deltas[peer]["confusion"] += deltas[student_name]["confusion"] * 0.35
                        diffused_deltas[peer]["confidence"] += deltas[student_name]["confidence"] * 0.35
                        diffused_deltas[peer]["stress"] += deltas[student_name]["stress"] * 0.35

        # Social friend circles influence
        for circle in FRIEND_CIRCLES:
            if student_name in circle:
                for peer in circle:
                    if peer != student_name and peer in diffused_deltas:
                        diffused_deltas[peer]["attention"] += deltas[student_name]["attention"] * 0.35
                        diffused_deltas[peer]["confusion"] += deltas[student_name]["confusion"] * 0.35
                        diffused_deltas[peer]["confidence"] += deltas[student_name]["confidence"] * 0.35
                        diffused_deltas[peer]["stress"] += deltas[student_name]["stress"] * 0.35

    # 3. Iterate and apply momentum + health monitor checks
    for state in student_states:
        name_lower = state.student_name.lower().strip()
        if state.student_name not in deltas:
            continue
            
        memory = get_student_memory(state)
        ds = memory.get("dynamic_state", {})
        relationships = memory.get("relationships", {})
        
        # A. Apply momentum-based evolution
        target_attention = max(10.0, min(100.0, state.attention_level + diffused_deltas[state.student_name]["attention"]))
        target_confusion = max(0.0, min(100.0, state.confusion_level + diffused_deltas[state.student_name]["confusion"]))
        target_confidence = max(10.0, min(100.0, state.confidence_level + diffused_deltas[state.student_name]["confidence"]))
        target_stress = max(0.0, min(100.0, ds.get("stress", 15.0) + diffused_deltas[state.student_name]["stress"]))
        
        # Calculate curiosity momentum target
        curiosity_delta = 0.0
        if is_question:
            curiosity_delta += 15.0
        if consecutive_teacher_turns >= 2:
            curiosity_delta -= 3.0 * consecutive_teacher_turns
        target_curiosity = max(10.0, min(100.0, state.curiosity_level + curiosity_delta))

        # Delta clamps (max single turn change is ±25)
        target_attention = state.attention_level + max(-25.0, min(25.0, target_attention - state.attention_level))
        target_confusion = state.confusion_level + max(-25.0, min(25.0, target_confusion - state.confusion_level))
        target_confidence = state.confidence_level + max(-25.0, min(25.0, target_confidence - state.confidence_level))
        target_stress = ds.get("stress", 15.0) + max(-25.0, min(25.0, target_stress - ds.get("stress", 15.0)))
        target_curiosity = state.curiosity_level + max(-25.0, min(25.0, target_curiosity - state.curiosity_level))

        # Momentum calculation: 0.8 old + 0.2 new
        state.attention_level = int(round(state.attention_level * 0.8 + target_attention * 0.2))
        state.confusion_level = int(round(state.confusion_level * 0.8 + target_confusion * 0.2))
        state.confidence_level = int(round(state.confidence_level * 0.8 + target_confidence * 0.2))
        state.curiosity_level = int(round(state.curiosity_level * 0.8 + target_curiosity * 0.2))
        ds["stress"] = float(round(ds.get("stress", 15.0) * 0.8 + target_stress * 0.2, 1))

        # Silence timeout protection checking
        did_speak = (last_student_sender == name_lower)
        from validation import SimulationValidationEngine
        ds = SimulationValidationEngine.check_silence_duration(state.student_name, did_speak, ds)
        
        # Decrement penalty turns if active
        penalty_turns = ds.get("interruption_penalty_turns", 0)
        if penalty_turns > 0:
            ds["interruption_penalty_turns"] = penalty_turns - 1

        # B. Health Monitor Auto-recovery for runaway emotions (>= 3 turns in critical state)
        critical_mood_turns = ds.get("critical_mood_turns", 0)
        if ds.get("mood", "normal") in ["stressed", "bored", "confused"]:
            critical_mood_turns += 1
        else:
            critical_mood_turns = 0
        ds["critical_mood_turns"] = critical_mood_turns

        if critical_mood_turns >= 3:
            print(f"[HEALTH MONITOR] Auto-correcting runaway emotion for {state.student_name} (turns: {critical_mood_turns})")
            state.attention_level = min(100, state.attention_level + 10)
            state.confusion_level = max(0, state.confusion_level - 12)
            ds["stress"] = max(0.0, ds["stress"] - 15.0)
            ds["critical_mood_turns"] = 0  # Reset recovery trigger

        # Hard clamps for all states
        state.attention_level = max(10, min(100, state.attention_level))
        state.confusion_level = max(0, min(100, state.confusion_level))
        state.confidence_level = max(10, min(100, state.confidence_level))
        ds["stress"] = max(0.0, min(100.0, ds["stress"]))

        # Set student mood
        if ds["stress"] > 60.0:
            ds["mood"] = "stressed"
        elif state.attention_level < 35:
            ds["mood"] = "bored"
        elif state.confusion_level > 55:
            ds["mood"] = "confused"
        else:
            ds["mood"] = "normal"

        # C. Evolve relationships slowly over time based on conversational feedback
        if last_student_sender:
            last_sender_name = last_student_sender.strip().title()
            if last_sender_name in relationships and last_sender_name != state.student_name:
                rel = relationships[last_sender_name]
                if isinstance(rel, dict) and "trust" in rel:
                    # Friendship circle reinforcement
                    is_friend = False
                    for circle in FRIEND_CIRCLES:
                        if state.student_name in circle and last_sender_name in circle:
                            is_friend = True
                            break
                    
                    if is_friend:
                        rel["friendship"] = min(100.0, rel["friendship"] + random.uniform(0.3, 1.2))
                        rel["influence"] = min(100.0, rel["influence"] + random.uniform(0.1, 0.8))
                        rel["trust"] = min(100.0, rel["trust"] + random.uniform(0.2, 0.8))
                    
                    # Interruption spreads annoyance and lowers trust
                    if last_sender_name.lower() in ["kabir", "ishaan"] and name_lower != "kabir" and name_lower != "ishaan":
                        rel["annoyance"] = min(100.0, rel["annoyance"] + random.uniform(0.5, 2.0))
                        rel["trust"] = max(0.0, rel["trust"] - random.uniform(0.2, 1.0))
                    
                    # Aarav asking smart questions boosts peer trust
                    if last_sender_name == "Aarav":
                        rel["trust"] = min(100.0, rel["trust"] + random.uniform(0.5, 1.5))
                        rel["supportiveness"] = min(100.0, rel["supportiveness"] + random.uniform(0.2, 0.8))

        # Apply slow relational drift/decay back to defaults (50/50/10/30/50)
        # 1.5% drift towards defaults per turn
        for peer_name, rel in relationships.items():
            if isinstance(rel, dict) and "trust" in rel:
                rel["trust"] = float(round(rel["trust"] * 0.985 + 50.0 * 0.015, 1))
                rel["friendship"] = float(round(rel["friendship"] * 0.985 + 50.0 * 0.015, 1))
                rel["annoyance"] = float(round(rel["annoyance"] * 0.985 + 10.0 * 0.015, 1))
                rel["influence"] = float(round(rel["influence"] * 0.985 + 30.0 * 0.015, 1))
                rel["supportiveness"] = float(round(rel["supportiveness"] * 0.985 + 50.0 * 0.015, 1))
                
        # Write back memory objects
        memory["dynamic_state"] = ds
        memory["relationships"] = relationships
        state.memory_json = json.dumps(memory, ensure_ascii=False)
        
        # Periodic memory compaction check
        prune_and_summarize_memory(state)
        
    db.commit()
    
    # Calculate previous noise and stress from database to apply momentum
    prev_noise = 30.0
    prev_stress = 20.0
    if db and len(student_states) > 0:
        try:
            session_id = student_states[0].session_id
            from models import SessionMessage
            last_checkpoint = db.query(SessionMessage).filter(
                SessionMessage.session_id == session_id,
                SessionMessage.sender_type == "state_checkpoint"
            ).order_by(SessionMessage.timestamp.desc()).first()
            if last_checkpoint:
                chk = json.loads(last_checkpoint.message_text)
                prev_noise = chk.get("noise", 30.0)
                prev_stress = chk.get("stress", 20.0)
        except Exception:
            pass

    # Momentum-based evolution of noise and stress (0.8 old + 0.2 new)
    final_noise = round(prev_noise * 0.8 + turn_noise * 0.2, 1)
    final_stress = round(prev_stress * 0.8 + turn_stress * 0.2, 1)

    final_noise = max(10.0, min(100.0, final_noise))
    final_stress = max(5.0, min(100.0, final_stress))
    return {"noise": final_noise, "stress": final_stress}
