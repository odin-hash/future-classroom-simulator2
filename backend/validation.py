import re
from typing import Dict, Any, List, Optional

def compute_jaccard_similarity(text1: str, text2: str) -> float:
    """Computes word-level Jaccard similarity between two texts."""
    words1 = set(re.findall(r'\w+', text1.lower()))
    words2 = set(re.findall(r'\w+', text2.lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


class SimulationValidationEngine:
    """
    Simulation Validation & Self-Healing Engine.
    Detects and auto-corrects repetitive outputs, unrealistic jumps,
    impossible indicators, excessive interruptions, and silent students.
    """

    @staticmethod
    def validate_and_heal_response(
        student_name: str,
        personality_role: str,
        response_text: str,
        last_responses: List[str],
        topic: str = "this topic"
    ) -> str:
        """
        Detects if the student response is repetitive (Jaccard similarity >= 0.8).
        If repetitive, auto-heals by returning an alternative character fallback text.
        """
        if not last_responses:
            return response_text

        is_repetitive = False
        for prev in last_responses:
            if compute_jaccard_similarity(response_text, prev) >= 0.8:
                is_repetitive = True
                break

        if not is_repetitive:
            return response_text

        print(f"[VALIDATOR] Repetitive response detected for {student_name}. Healing...")

        # Personality-specific unique fallback templates to break loops
        healed_options = {
            "Curious student": [
                f"Umm, wait, so how does that connect to what we learned about {topic} earlier?",
                f"Actually, I was thinking... is there, like, any exception to this for {topic}?",
                f"Oh, that's interesting! But, uh, why does that happen in this specific way?",
                f"I was reading about {topic}... can it be used in other subjects too?",
                f"Can you, like, explain the main difference between this and similar ideas in {topic}?",
                f"Wait, is there a real-world example where this part of {topic} fails?"
            ],
            "Shy student": [
                f"Um... okay... I think I understand {topic} a bit better now...",
                f"...sorry, I was just... writing down what you said about {topic}...",
                f"Um, maybe... is it, uh, related to the explanation you just gave?",
                f"I'm not sure, but... maybe {topic} has other rules too...",
                f"Um... sorry, could you explain that one more time?",
                f"I think... I need to practice {topic} a bit more to understand..."
            ],
            "Distracted student": [
                f"Wait, what? Are we still talking about {topic}? Sorry, I got lost...",
                f"Huh? Oh, I was, uh, looking at something else. What page are we on?",
                f"Sorry, could you repeat that? I wasn't... listening closely...",
                f"Oh, sorry! I was just, like, organizing my notes on {topic}.",
                f"Wait... did I miss the explanation of {topic}?",
                f"Is this going to be on the test? Sorry, I zoned out..."
            ],
            "Hyperactive student": [
                f"OH! Can we try making a model or, like, doing an experiment for {topic}?! Please?!",
                f"PICK ME! I have, uh, another idea about how {topic} works!!",
                f"This is so cool!! Can we search for a video about {topic} right now?!",
                f"Let's do a race to see who can solve a {topic} problem first! Wait, can we?",
                f"Wait! I have a really funny story about {topic}!",
                f"Can we write our own examples for {topic} on the board? Pleeease!"
            ],
            "Weak learner": [
                f"Teacher, I'm still a bit confused about {topic}. Can we... do another simple example?",
                f"Could you explain that last part about {topic} again? I didn't... quite get it...",
                f"Is that like the example we did yesterday? I'm, uh, trying to follow...",
                f"Can we slow down a little bit on {topic}? I'm still writing it down...",
                f"Um, sorry, I didn't understand how you got that result for {topic}.",
                f"Is there, like, a simpler way to think about {topic}?"
            ],
            "Overconfident student": [
                f"Pfft, {topic} is like, super easy anyway. I already knew all of this.",
                f"Obviously! My older brother, uh, told me about {topic} last week.",
                f"This is basic. Can we move on to something, like, more advanced?",
                f"I could, uh, explain {topic} to the class if you want, teacher.",
                f"Loops are just simple logic. I mastered this ages ago.",
                f"I think I can write a faster version of {topic} than this, honestly."
            ]
        }

        fallbacks = healed_options.get(
            personality_role, 
            [f"I see, so that is how {topic} works...", f"Okay, I am following the lesson on {topic}."]
        )
        
        # Select a fallback that is not in the last_responses list
        for f in fallbacks:
            if not any(compute_jaccard_similarity(f, prev) >= 0.8 for prev in last_responses):
                return f
        
        return fallbacks[0]

    @staticmethod
    def reconcile_classroom_state(
        attention: float,
        engagement: float,
        confusion: float
    ) -> float:
        """
        Maintains consistency between classroom-level indicators.
        Engagement and attention must move together, and high confusion dampens engagement.
        """
        # Engagement cannot diverge from attention by more than 25 units
        if engagement > attention + 25.0:
            engagement = attention + 25.0
        elif engagement < attention - 25.0:
            engagement = attention - 25.0

        # High confusion overrides and dampens engagement
        if confusion > 60.0 and engagement > 70.0:
            engagement -= 15.0

        return round(max(0.0, min(100.0, engagement)), 1)

    @staticmethod
    def apply_interruption_rules(
        student_name: str,
        current_turn: int,
        dynamic_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Checks student interruption frequency.
        If a student has interrupted >= 3 times in their history, set penalty turns.
        """
        # Keep a list of turns where they interrupted
        interruption_history = dynamic_state.get("interruption_turns", [])
        
        # Record this turn if student interrupted
        # Note: calling function should append to history if student just interrupted
        
        # Clean history to keep only last 10 turns
        recent_interrupts = [t for t in interruption_history if current_turn - t <= 8]
        dynamic_state["interruption_turns"] = recent_interrupts

        # Apply penalty if they interrupted >= 3 times in the last 8 turns
        if len(recent_interrupts) >= 3:
            print(f"[VALIDATOR] Excessive interruptions ({len(recent_interrupts)}) detected for {student_name}. Applying penalty.")
            dynamic_state["interruption_penalty_turns"] = 3
        
        return dynamic_state

    @staticmethod
    def check_silence_duration(
        student_name: str,
        did_speak: bool,
        dynamic_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tracks silent periods. Increments silence turns counter.
        Silences >= 15 turns trigger volunteer boosts.
        """
        turns_since_spoken = dynamic_state.get("turns_since_spoken", 0)
        
        if did_speak:
            turns_since_spoken = 0
        else:
            turns_since_spoken += 1
            
        dynamic_state["turns_since_spoken"] = turns_since_spoken
        
        if turns_since_spoken >= 15:
            print(f"[VALIDATOR] Student {student_name} has been silent for {turns_since_spoken} turns. Elevating volunteer interest.")
            
        return dynamic_state
