import random
from typing import List, Dict, Any, Optional

# List of 6 students with specific personas and seating positions
STUDENTS = [
    {
        "name": "Aarav",
        "personality": "Curious student",
        "description": "Asks deep, unexpected, and sometimes advanced questions about the topic. Highly engaged.",
        "seat_row": 1,
        "seat_col": 1,
        "avatar_style": "curious-boy"
    },
    {
        "name": "Ananya",
        "personality": "Shy student",
        "description": "Quiet, rarely speaks unless called by name. Gives short, nervous responses.",
        "seat_row": 1,
        "seat_col": 2,
        "avatar_style": "shy-girl"
    },
    {
        "name": "Vihaan",
        "personality": "Distracted student",
        "description": "Loses focus easily, doodles, or whispers. Needs reminders to stay on task.",
        "seat_row": 1,
        "seat_col": 3,
        "avatar_style": "distracted-boy"
    },
    {
        "name": "Ishaan",
        "personality": "Hyperactive student",
        "description": "Interrupts frequently, speaks out of turn, and answers enthusiastically without being asked.",
        "seat_row": 2,
        "seat_col": 1,
        "avatar_style": "hyperactive-boy"
    },
    {
        "name": "Riya",
        "personality": "Weak learner",
        "description": "Needs repeated, simple explanations. Easily confused by complex vocabulary.",
        "seat_row": 2,
        "seat_col": 2,
        "avatar_style": "weak-learner-girl"
    },
    {
        "name": "Kabir",
        "personality": "Overconfident student",
        "description": "Answers quickly, confidently, and often incorrectly. Needs gentle guidance to realize mistakes.",
        "seat_row": 2,
        "seat_col": 3,
        "avatar_style": "overconfident-boy"
    }
]

# Random events that can disrupt the classroom
CLASSROOM_EVENTS = [
    {
        "id": "whispering",
        "title": "Students Whispering",
        "description": "Vihaan and Ishaan are whispering about video games in the back row.",
        "severity": "medium",
        "affected_students": ["Vihaan", "Ishaan"],
        "instructions": "Remind them to focus or ask them a direct question about the lesson."
    },
    {
        "id": "attention_drop",
        "title": "Attention Drop",
        "description": "Vihaan and Ananya look sleepy and are losing focus on the presentation.",
        "severity": "low",
        "affected_students": ["Vihaan", "Ananya"],
        "instructions": "Use a warm-up activity, change your teaching method, or call on them to participate."
    },
    {
        "id": "difficult_question",
        "title": "Difficult Question",
        "description": "Aarav raises his hand and asks an advanced question that is slightly out of scope.",
        "severity": "medium",
        "affected_students": ["Aarav"],
        "instructions": "Acknowledge the question, answer it concisely, or offer to discuss it after class."
    },
    {
        "id": "confusion",
        "title": "Widespread Confusion",
        "description": "Riya and Kabir look blankly at the board, indicating they didn't follow the explanation.",
        "severity": "high",
        "affected_students": ["Riya", "Kabir"],
        "instructions": "Break down the concept, use an analogy, or ask them what part is unclear."
    },
    {
        "id": "interruption",
        "title": "Hyperactive Interruption",
        "description": "Ishaan stands up and interrupts to share an unrelated personal story.",
        "severity": "medium",
        "affected_students": ["Ishaan"],
        "instructions": "Politely ask Ishaan to wait until the explanation is finished."
    },
    {
        "id": "technical_issue",
        "title": "Technical Audio Glitch",
        "description": "A static sound comes from Riya's virtual desk. She is trying to speak but is muted.",
        "severity": "low",
        "affected_students": ["Riya"],
        "instructions": "Ask her to check her settings or type her answer in the chat box."
    },
    {
        "id": "forgets_homework",
        "title": "Homework Forgotten",
        "description": "Riya looks highly anxious. She admits she forgot to do the homework assignment.",
        "severity": "medium",
        "affected_students": ["Riya"],
        "instructions": "Acknowledge her honesty, support her, or ask her to follow up after class."
    },
    {
        "id": "notebook_falls",
        "title": "Notebook Drops",
        "description": "A sudden loud crash as Vihaan's heavy textbook slides off his desk and falls.",
        "severity": "low",
        "affected_students": ["Vihaan"],
        "instructions": "Calmly refocus the class attention back to the blackboard canvas."
    },
    {
        "id": "projector_stops",
        "title": "Projector Glitch",
        "description": "The overhead classroom presentation projector screen flickers and goes completely blank.",
        "severity": "high",
        "affected_students": ["Aarav", "Kabir"],
        "instructions": "Take a moment to describe the concept verbally or draw a quick diagram on the board."
    },
    {
        "id": "late_entry",
        "title": "Late Arrival",
        "description": "A sudden knock at the door as Kabir enters the classroom late, distracting the students.",
        "severity": "medium",
        "affected_students": ["Kabir"],
        "instructions": "Welcome Kabir quickly, tell him what topic is being covered, and proceed."
    },
    {
        "id": "bell_rings",
        "title": "Classroom Bell Rings",
        "description": "The school bell rings loudly, signaling that class time is up and students are eager to pack their bags.",
        "severity": "medium",
        "affected_students": ["Vihaan", "Ishaan", "Kabir"],
        "instructions": "Wrap up the lecture quickly, summarize the key takeaways, and dismiss the students."
    }
]


def select_responding_student(teacher_input: str, addressed_student: Optional[str] = None) -> Dict[str, Any]:
    """
    Selects which student should respond to the teacher's input.
    Supports both UI names and custom task-requested names.
    """
    # 1. If a student is explicitly addressed, select them
    if addressed_student:
        for s in STUDENTS:
            if s["name"].lower() == addressed_student.lower():
                return s

    # 2. Check keywords in teacher's input to find if they mentioned any student name
    input_lower = teacher_input.lower()
    for s in STUDENTS:
        if s["name"].lower() in input_lower:
            return s

    # 3. Add custom mapping for newly requested task names
    task_mappings = {
        "arjun": "Aarav",
        "priya": "Ananya",
        "rahul": "Vihaan",
        "neha": "Riya",
    }
    for key, target_name in task_mappings.items():
        if key in input_lower:
            for s in STUDENTS:
                if s["name"] == target_name:
                    return s

    # 4. Else, look for general triggers
    # If it's a question (ends with '?'), choose between Kabir (overconfident), Ishaan (hyperactive), or Aarav (curious)
    if teacher_input.strip().endswith("?") or "what" in input_lower or "how" in input_lower or "why" in input_lower:
        choices = [s for s in STUDENTS if s["name"] in ["Kabir", "Ishaan", "Aarav", "Riya"]]
        return random.choice(choices)

    # 5. Otherwise, pick a random student
    return random.choice(STUDENTS)


# Map event ID to category to prevent consecutive category triggers
EVENT_CATEGORIES = {
    "technical_issue": "technical",
    "projector_stops": "technical",
    "whispering": "social",
    "attention_drop": "social",
    "interruption": "social",
    "confusion": "learning",
    "difficult_question": "learning",
    "forgets_homework": "learning",
    "notebook_falls": "environmental",
    "late_entry": "environmental",
    "bell_rings": "environmental"
}


def trigger_random_event(
    current_turn: int,
    classroom_state: Optional[Dict[str, Any]] = None,
    last_event_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Decides whether to trigger a random classroom event based on state-dependent probabilities
    computed independently for four categories: Technical, Social, Learning, and Environmental.
    Selects at most one triggered event in order of priority (Social > Learning > Technical > Environmental).
    Prevents triggering the same category or event ID in consecutive turns.
    """
    if current_turn <= 1:
        return None

    import random

    noise = 30.0
    attention = 75.0
    stress = 20.0
    confusion = 25.0

    if classroom_state:
        noise = classroom_state.get("noise", 30.0)
        attention = classroom_state.get("attention", 75.0)
        stress = classroom_state.get("stress", 20.0)
        confusion = classroom_state.get("confusion", 25.0)

    last_category = EVENT_CATEGORIES.get(last_event_id) if last_event_id else None

    # 1. Roll Technical Event (Base: 3%)
    tech_prob = 0.03

    # 2. Roll Social Event (Base: 8%)
    social_prob = 0.08
    if noise > 55.0 or attention < 50.0:
        social_prob = 0.18

    # 3. Roll Learning Event (Base: 10%)
    learning_prob = 0.10
    if confusion > 55.0 or stress > 50.0:
        learning_prob = 0.22

    # 4. Roll Environmental Event (Base: 5%)
    env_prob = 0.05
    if current_turn >= 10:  # Class is finishing
        env_prob = 0.18

    triggered = {}

    # Technical roll
    if last_category != "technical" and random.random() < tech_prob:
        tech_events = [e for e in CLASSROOM_EVENTS if e["id"] in ["technical_issue", "projector_stops"] and e["id"] != last_event_id]
        if tech_events:
            triggered["technical"] = random.choice(tech_events)

    # Social roll
    if last_category != "social" and random.random() < social_prob:
        social_events = [e for e in CLASSROOM_EVENTS if e["id"] in ["whispering", "attention_drop", "interruption"] and e["id"] != last_event_id]
        if social_events:
            triggered["social"] = random.choice(social_events)

    # Learning roll
    if last_category != "learning" and random.random() < learning_prob:
        learning_events = [e for e in CLASSROOM_EVENTS if e["id"] in ["confusion", "difficult_question", "forgets_homework"] and e["id"] != last_event_id]
        if learning_events:
            triggered["learning"] = random.choice(learning_events)

    # Environmental roll
    if last_category != "environmental" and random.random() < env_prob:
        env_ids = ["notebook_falls"]
        if current_turn <= 4:
            env_ids.append("late_entry")
        if current_turn >= 10:
            env_ids.append("bell_rings")
            
        env_events = [e for e in CLASSROOM_EVENTS if e["id"] in env_ids and e["id"] != last_event_id]
        if env_events:
            triggered["environmental"] = random.choice(env_events)

    # Prioritize which event to fire if multiple rolled successfully
    # Social > Learning > Technical > Environmental
    if "social" in triggered:
        return triggered["social"]
    elif "learning" in triggered:
        return triggered["learning"]
    elif "technical" in triggered:
        return triggered["technical"]
    elif "environmental" in triggered:
        return triggered["environmental"]

    return None
