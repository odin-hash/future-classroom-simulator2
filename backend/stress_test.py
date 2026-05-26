import os
import sys
import time
import json
import asyncio
from typing import Dict, Any, List

# Set DATABASE_URL before importing anything from database/main to isolate the test database
TEST_DB_PATH = "./classroom_stress_test.db"
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception as e:
        print(f"Warning: Could not remove existing test database: {e}")

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

# Dynamically add the backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base, engine, SessionLocal
from models import StudentState, SessionMessage
from main import create_session, process_teacher_turn, end_session
from schemas import ClassroomSessionCreate, TeacherTurnInput
from validation import compute_jaccard_similarity
from simulation import STUDENTS


async def run_stress_test():
    print("======================================================================")
    print("🚀 STARTING AUTOMATED 60-TURN CLASSROOM SIMULATION STRESS TEST")
    print("======================================================================")

    # 1. Initialize Test Database
    print("[TEST SETUP] Initializing clean SQLite database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # 2. Create Classroom Session
    session_data = ClassroomSessionCreate(
        subject="Computer Science",
        topic="Python Loops",
        class_level="Grade 10",
        lesson_objectives="Understand for and while loops, infinite loops, and break/continue statements.",
        teaching_method="Interactive Discussion",
        duration_minutes=30,
        language="English"
    )
    print("[TEST SETUP] Creating new classroom session...")
    session = create_session(session_data, db)
    session_id = session.id
    print(f"[TEST SETUP] Session created successfully with ID: {session_id}")

    # 3. Setup 60 turns representing 4 pedagogical phases
    teacher_turns: List[TeacherTurnInput] = []

    # Phase 1: Normal Lecture (Turns 1-15)
    for i in range(1, 16):
        if i == 5:
            teacher_turns.append(TeacherTurnInput(
                message="Aarav, can you give me an example of a loop in daily life?",
                addressed_student="Aarav",
                action="ask_question"
            ))
        elif i == 10:
            teacher_turns.append(TeacherTurnInput(
                message="Ananya, why might we want to use a loop instead of copying code?",
                addressed_student="Ananya",
                action="ask_question"
            ))
        elif i == 12:
            teacher_turns.append(TeacherTurnInput(
                message="Great. Let's look at how a simple for loop is written in Python.",
                action="explain_basic"
            ))
        else:
            teacher_turns.append(TeacherTurnInput(
                message=f"In programming, loops allow us to repeat a block of code multiple times. This is turn {i} of our introduction.",
                action="lecture"
            ))

    # Phase 2: Rapid Questioning & Complexity/Confusion (Turns 16-30)
    for i in range(16, 31):
        if i == 20:
            teacher_turns.append(TeacherTurnInput(
                message="Riya, if we have nested loops where the inner loop runs N times and the outer loop runs N times, what is the complexity?",
                addressed_student="Riya",
                action="ask_question"
            ))
        elif i == 25:
            teacher_turns.append(TeacherTurnInput(
                message="Kabir, how do generator expressions in loops compare to list comprehensions regarding memory overhead?",
                addressed_student="Kabir",
                action="ask_question"
            ))
        else:
            teacher_turns.append(TeacherTurnInput(
                message=f"Let's dive into nested loops, algorithmic time complexity analysis, and multi-dimensional matrices. Turn {i}.",
                action="explain_complex"
            ))

    # Phase 3: Noisy Classroom & High Interruptions (Turns 31-45)
    for i in range(31, 46):
        if i == 35:
            teacher_turns.append(TeacherTurnInput(
                message="Ishaan, please stop interrupting and raise your hand.",
                addressed_student="Ishaan",
                action="warn"
            ))
        elif i == 40:
            teacher_turns.append(TeacherTurnInput(
                message="Class, please pay attention to the screen and quiet down.",
                action="focus"
            ))
        else:
            teacher_turns.append(TeacherTurnInput(
                message=f"Continuing our lesson on loops, we will now look at how to control loop execution. Turn {i}.",
                action="lecture"
            ))

    # Phase 4: Low Attention & Boredom Recovery (Turns 46-60)
    for i in range(46, 61):
        if i <= 52:
            # Monotonous direct reading of slides to induce low attention
            teacher_turns.append(TeacherTurnInput(
                message=f"Reading slides: loops repeat code. Syntax is for variable in range. Slide line {i}.",
                action="lecture"
            ))
        elif i == 53:
            # Recovery trigger
            teacher_turns.append(TeacherTurnInput(
                message="Okay class, let's play a quick coding trivia game to test what we know about loops!",
                action="re-engage"
            ))
        else:
            teacher_turns.append(TeacherTurnInput(
                message=f"Awesome work on the game! Now let's summarize what we learned today. Turn {i}.",
                action="lecture"
            ))

    # 4. Run the 60-turn simulation loop and record metrics
    turn_metrics = []
    runaway_state_failures = 0
    repetitive_responses = 0
    consecutive_repetitions = 0

    # Dictionaries to track student consecutive states for runaway detection
    student_low_attention_turns = {s["name"]: 0 for s in STUDENTS}
    student_high_confusion_turns = {s["name"]: 0 for s in STUDENTS}
    
    # Store responses history per student to verify Jaccard duplicates
    student_response_history = {s["name"]: [] for s in STUDENTS}

    print(f"\n🏃 Running {len(teacher_turns)} turns...")
    for idx, turn_input in enumerate(teacher_turns):
        turn_num = idx + 1
        print(f"👉 [TURN {turn_num}/60] Teacher: {turn_input.message[:60]}... (Action: {turn_input.action or 'none'})")
        
        start_time = time.time()
        
        try:
            # Execute turn
            turn_result = await process_teacher_turn(session_id, turn_input, db)
            latency = time.time() - start_time
            
            # Query student states from DB
            student_states = db.query(StudentState).filter(StudentState.session_id == session_id).all()
            
            # Gather state metrics
            states_info = {}
            memory_sizes = {}
            for state in student_states:
                name = state.student_name
                states_info[name] = {
                    "attention": state.attention_level,
                    "confusion": state.confusion_level,
                    "confidence": state.confidence_level,
                    "understanding": state.understanding_level,
                }
                memory_sizes[name] = len(state.memory_json) if state.memory_json else 0

                # Runaway State failure checks:
                # Did they stay at absolute minimum attention (10) for more than 3 turns?
                if state.attention_level <= 10:
                    student_low_attention_turns[name] += 1
                else:
                    student_low_attention_turns[name] = 0

                # Did they stay at absolute maximum confusion (100) for more than 3 turns?
                if state.confusion_level >= 100:
                    student_high_confusion_turns[name] += 1
                else:
                    student_high_confusion_turns[name] = 0

                if student_low_attention_turns[name] > 3:
                    print(f"⚠️ [RUNAWAY DETECTED] {name} attention level stuck at 10 for {student_low_attention_turns[name]} turns!")
                    runaway_state_failures += 1
                if student_high_confusion_turns[name] > 3:
                    print(f"⚠️ [RUNAWAY DETECTED] {name} confusion level stuck at 100 for {student_high_confusion_turns[name]} turns!")
                    runaway_state_failures += 1

            # Check response repetition via Jaccard
            student_msg = turn_result.get("student_message", {})
            responder_name = student_msg.get("sender_name")
            response_text = student_msg.get("message_text", "")
            
            is_dup = False
            is_consec_dup = False
            if responder_name and response_text:
                prev_responses = student_response_history[responder_name]
                if prev_responses:
                    # Check consecutive duplicate
                    consec_sim = compute_jaccard_similarity(response_text, prev_responses[-1])
                    if consec_sim >= 0.8:
                        is_consec_dup = True
                        consecutive_repetitions += 1
                        print(f"⚠️ [CONSECUTIVE REPETITION DETECTED] {responder_name} repeated response consecutively (Jaccard: {consec_sim:.2f})!")

                    # Check any duplicate in last 5
                    for prev in prev_responses[-5:]:
                        sim = compute_jaccard_similarity(response_text, prev)
                        if sim >= 0.8:
                            is_dup = True
                            repetitive_responses += 1
                            print(f"⚠️ [REPETITION DETECTED] {responder_name} repeated response (Jaccard: {sim:.2f})!")
                            break
                student_response_history[responder_name].append(response_text)

            # Record turn details
            turn_metrics.append({
                "turn": turn_num,
                "latency_sec": latency,
                "responder": responder_name,
                "event_triggered": turn_result.get("triggered_event"),
                "classroom_state": turn_result.get("classroom_state"),
                "student_states": states_info,
                "memory_sizes": memory_sizes,
                "is_duplicate_response": is_dup,
                "is_consecutive_duplicate": is_consec_dup
            })
            
        except Exception as e:
            print(f"❌ Exception occurred on Turn {turn_num}: {e}")
            import traceback
            traceback.print_exc()
            turn_metrics.append({
                "turn": turn_num,
                "error": str(e)
            })

    # 5. End Session & Collect Analytics
    print("\n🏁 Ending session and compiling pedagogical analytics...")
    analytics_result = await end_session(session_id, db)
    
    # 6. Extract Realism Score & Suggestions
    suggestions_md = analytics_result.suggestions or ""
    print(f"Suggestions report size: {len(suggestions_md)} characters.")
    
    realism_score = 0.0
    for line in suggestions_md.split("\n"):
        if "Realism Score:" in line or "🔬 Simulation Realism Report" in line or "Realism" in line:
            print(f"Report line: {line}")
        # Try to parse realism score if it is explicitly outputted (supporting Markdown formatting)
        import re as _re
        match = _re.search(r"Realism Score[\*\s:]+([\d\.]+)", line)
        if match:
            realism_score = float(match.group(1))

    # Calculate statistics
    latencies = [m["latency_sec"] for m in turn_metrics if "latency_sec" in m]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    
    all_mem_sizes = []
    for m in turn_metrics:
        if "memory_sizes" in m:
            all_mem_sizes.extend(m["memory_sizes"].values())
            
    avg_mem_size = sum(all_mem_sizes) / len(all_mem_sizes) if all_mem_sizes else 0.0
    max_mem_size = max(all_mem_sizes) if all_mem_sizes else 0.0

    print("\n======================================================================")
    print("🔬 STRESS TEST SUMMARY REPORT")
    print("======================================================================")
    print(f"Total Turns Run:         {len(turn_metrics)}")
    print(f"Average Turn Latency:    {avg_latency:.4f} seconds")
    print(f"Maximum Turn Latency:    {max_latency:.4f} seconds")
    print(f"Average memory_json size: {avg_mem_size:.1f} bytes")
    print(f"Maximum memory_json size: {max_mem_size:.1f} bytes")
    print(f"Runaway State Failures:  {runaway_state_failures}")
    print(f"Consecutive Repetitions: {consecutive_repetitions}")
    print(f"Total Repetitive Responses (within last 5): {repetitive_responses}")
    print(f"Parsed Realism Score:    {realism_score:.2f}/10.0")

    # Set validation conditions
    pass_flag = True
    reasons = []
    
    if runaway_state_failures > 0:
        pass_flag = False
        reasons.append("Runaway state failures occurred (stuck emotions).")
        
    if consecutive_repetitions > 0:
        pass_flag = False
        reasons.append("Consecutive repetitive responses detected (student stuck in response loop).")

    # In offline fallback template mode, students are expected to repeat some template responses
    # over a long 60-turn session. We allow up to 20 total duplicate responses.
    if repetitive_responses > 20:
        pass_flag = False
        reasons.append("Too many total duplicate replies (>20) even with dynamic template selection.")
        
    if max_mem_size > 15000:  # If compaction works, size should stay bounded
        pass_flag = False
        reasons.append("Memory size grew too large (compactor failure).")

    # Clean up test database file
    db.close()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
            print("[TEST CLEANUP] Deleted test database classroom_stress_test.db")
        except Exception as e:
            print(f"Warning: Could not delete test database: {e}")

    report = {
        "status": "PASSED" if pass_flag else "FAILED",
        "failures": reasons,
        "metrics": {
            "total_turns": len(turn_metrics),
            "average_latency_sec": avg_latency,
            "maximum_latency_sec": max_latency,
            "average_memory_json_bytes": avg_mem_size,
            "maximum_memory_json_bytes": max_mem_size,
            "runaway_state_failures": runaway_state_failures,
            "consecutive_repetitions": consecutive_repetitions,
            "repetitive_responses": repetitive_responses,
            "realism_score": realism_score
        },
        "detailed_turns": turn_metrics
    }

    # Save to JSON
    with open("stress_test_results.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\n💾 Saved test report to stress_test_results.json")
    print(f"FINAL RESULT: {'✅ PASS' if pass_flag else '❌ FAIL'}")
    print("======================================================================")
    
    if not pass_flag:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_stress_test())
