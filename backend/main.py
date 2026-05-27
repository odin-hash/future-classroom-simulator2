import os
import sys

# Dynamically add the backend directory to sys.path to support imports from both root and subdirectories
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import random
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import engine, get_db, Base
from models import ClassroomSession, SessionMessage, SessionAnalytics, StudentState
from schemas import (
    ClassroomSessionCreate,
    ClassroomSessionOut,
    SessionMessageCreate,
    SessionMessageOut,
    SessionAnalyticsCreate,
    SessionAnalyticsOut,
    TeacherTurnInput,
)
from simulation import STUDENTS, CLASSROOM_EVENTS, select_responding_student, trigger_random_event
from ai import generate_student_reply, generate_evaluation
from personality import (
    STUDENT_PERSONALITIES,
    select_responders,
    compute_classroom_state,
    apply_attention_decay,
    evolve_states_and_relationships,
)
from fastapi.responses import FileResponse
from voice import generate_speech_audio

# Initialize database tables
try:
    db_reset = os.environ.get("DB_RESET", "false").lower() == "true"
    if db_reset:
        print("[DB] DB_RESET is active. Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)
        print("[DB] Tables dropped successfully.")
    
    Base.metadata.create_all(bind=engine)
    print("[DB] Database tables initialized via metadata create_all.")
except Exception as table_err:
    print(f"[DB] Metadata create_all warning: {table_err}")

# Auto-migrate: Ensure newly added columns exist in deployed database (e.g. Postgres on Render)
# We execute each ALTER TABLE in its own independent transaction block to prevent failed
# columns (e.g. columns that already exist) from aborting the SQL transaction for other columns.
from sqlalchemy import text
for table, col_name, col_type in [
    ("student_states", "curiosity_level", "INTEGER DEFAULT 50"),
    ("student_states", "interrupt_probability", "INTEGER DEFAULT 20"),
    ("student_states", "memory_json", "TEXT"),
    ("sessions", "language", "VARCHAR(50) DEFAULT 'English'"),
    ("sessions", "lesson_objectives", "TEXT"),
    ("sessions", "teaching_method", "VARCHAR(100)"),
    ("sessions", "scenario", "VARCHAR(100) DEFAULT 'normal'"),
    ("session_messages", "student_personality", "VARCHAR(100)"),
]:
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        print(f"[DB] Auto-migration: Successfully added column {col_name} to {table}.")
    except Exception as col_err:
        # Ignore errors (column likely already exists or table does not exist)
        pass

app = FastAPI(title="Future Classroom Simulator API")

# Configure CORS for Vite Frontend with explicit allowed origins
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
if allowed_origins_env:
    origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://future-classroom-simulator.vercel.app",
        "https://future-classroom-simulator-git-main-odin-hash.vercel.app",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Cache", "Content-Length"]
)



@app.get("/")
def read_root():
    return {"message": "Welcome to Future Classroom Simulator API"}


@app.get("/api/students")
def get_students():
    """Returns details of virtual students"""
    return STUDENTS


@app.get("/api/events")
def get_events():
    """Returns details of possible classroom events"""
    return CLASSROOM_EVENTS


@app.post("/api/sessions", response_model=ClassroomSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(session_data: ClassroomSessionCreate, db: Session = Depends(get_db)):
    """Creates a new simulation session"""
    print(f"[CREATE SESSION] session_data: {session_data.model_dump()}")
    scenario = session_data.scenario or "normal"
    db_session = ClassroomSession(
        subject=session_data.subject,
        topic=session_data.topic,
        class_level=session_data.class_level,
        lesson_objectives=session_data.lesson_objectives,
        teaching_method=session_data.teaching_method,
        duration_minutes=session_data.duration_minutes,
        language=session_data.language,
        scenario=scenario,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    # Populate initial StudentState for each of the 6 students (using scenario overrides)
    import json as _json
    for s_info in STUDENTS:
        personality = STUDENT_PERSONALITIES.get(s_info["name"], {})
        traits = personality.get("traits", {})
        
        # Scenario baseline overrides
        att = traits.get("attention_base", 75)
        conf = traits.get("confidence", 65)
        und = 75
        confu = traits.get("confusion_base", 25)
        cur = traits.get("curiosity", 50)
        intr = traits.get("interrupt_probability", 20)
        
        if scenario == "low_attention":
            att = 25
        elif scenario == "high_confusion":
            confu = 80
            und = 25
            att = 65
        elif scenario == "noisy":
            att = 45
            confu = 40
        elif scenario == "hyperactive":
            cur = min(100, cur + 30)
            intr = min(100, intr + 30)
            if s_info["name"] in ["Ishaan", "Kabir"]:
                intr = 90
                cur = 95
        elif scenario == "time_pressure":
            att = 65
            confu = 30

        state = StudentState(
            session_id=db_session.id,
            student_name=s_info["name"],
            attention_level=att,
            confidence_level=conf,
            understanding_level=und,
            confusion_level=confu,
            curiosity_level=cur,
            interrupt_probability=intr,
            memory_summary=f"Class started. Topic: {db_session.topic}.",
            memory_json=_json.dumps({
                "concepts_taught": [],
                "questions_asked_by_student": [],
                "questions_received_from_teacher": [],
                "key_interactions": [],
                "last_responses": [],
            }),
        )
        db.add(state)
    
    db.commit()
    db.refresh(db_session)
    return db_session


@app.get("/api/sessions", response_model=List[ClassroomSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    """Lists all past sessions ordered by creation date desc"""
    return db.query(ClassroomSession).order_by(ClassroomSession.created_at.desc()).all()


@app.get("/api/sessions/{session_id}", response_model=ClassroomSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """Gets details and message history of a specific session"""
    db_session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Auto-initialize states for existing sessions without student_states
    if not db_session.student_states:
        import json as _json
        for s_info in STUDENTS:
            personality = STUDENT_PERSONALITIES.get(s_info["name"], {})
            traits = personality.get("traits", {})
            state = StudentState(
                session_id=db_session.id,
                student_name=s_info["name"],
                attention_level=traits.get("attention_base", 75),
                confidence_level=traits.get("confidence", 65),
                understanding_level=75,
                confusion_level=traits.get("confusion_base", 25),
                curiosity_level=traits.get("curiosity", 50),
                interrupt_probability=traits.get("interrupt_probability", 20),
                memory_summary=f"Class started. Topic: {db_session.topic}.",
                memory_json=_json.dumps({
                    "concepts_taught": [],
                    "questions_asked_by_student": [],
                    "questions_received_from_teacher": [],
                    "key_interactions": [],
                    "last_responses": [],
                }),
            )
            db.add(state)
        db.commit()
        db.refresh(db_session)
        
    return db_session


@app.get("/api/sessions/{session_id}/state")
def get_session_state(session_id: int, db: Session = Depends(get_db)):
    """
    Returns the unified recovery payload for a session, including active event,
    responder queue, elapsed ratio, student states, and the session configuration.
    """
    db_session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    latest_state_msg = db.query(SessionMessage).filter(
        SessionMessage.session_id == session_id,
        SessionMessage.sender_type == "session_state"
    ).order_by(SessionMessage.timestamp.desc()).first()
    
    state_data = {
        "active_event_id": None,
        "responder_queue": [],
        "elapsed_ratio": 0.0
    }
    
    if latest_state_msg:
        try:
            import json as _json
            state_data = _json.loads(latest_state_msg.message_text)
        except Exception:
            pass

    student_states = db.query(StudentState).filter(StudentState.session_id == session_id).all()
    student_states_serialized = []
    for s in student_states:
        try:
            mem_size = len(s.memory_json) if s.memory_json else 0
        except Exception:
            mem_size = 0
            
        student_states_serialized.append({
            "student_name": s.student_name,
            "attention_level": s.attention_level,
            "confidence_level": s.confidence_level,
            "understanding_level": s.understanding_level,
            "confusion_level": s.confusion_level,
            "memory_summary": s.memory_summary,
            "memory_size_bytes": mem_size,
            "participation_count": s.participation_count
        })

    last_checkpoint = db.query(SessionMessage).filter(
        SessionMessage.session_id == session_id,
        SessionMessage.sender_type == "state_checkpoint"
    ).order_by(SessionMessage.timestamp.desc()).first()
    
    classroom_state = {
        "noise": 30,
        "stress": 20,
        "attention": 75,
        "confusion": 25,
        "curiosity": 50,
        "energy": 60,
        "engagement": 70
    }
    if last_checkpoint:
        try:
            import json as _json
            classroom_state = _json.loads(last_checkpoint.message_text)
        except Exception:
            pass

    active_event_obj = None
    if state_data.get("active_event_id"):
        matching_events = [e for e in CLASSROOM_EVENTS if e["id"] == state_data["active_event_id"]]
        if matching_events:
            active_event_obj = matching_events[0]

    return {
        "session_id": session_id,
        "subject": db_session.subject,
        "topic": db_session.topic,
        "class_level": db_session.class_level,
        "duration_minutes": db_session.duration_minutes,
        "language": db_session.language,
        "active_event_id": state_data.get("active_event_id"),
        "active_event": active_event_obj,
        "responder_queue": state_data.get("responder_queue", []),
        "elapsed_ratio": state_data.get("elapsed_ratio", 0.0),
        "student_states": student_states_serialized,
        "classroom_state": classroom_state
    }



@app.post("/api/sessions/{session_id}/turns")
async def process_teacher_turn(
    session_id: int,
    turn_input: TeacherTurnInput,
    db: Session = Depends(get_db)
):
    """
    Main turn processing endpoint. Receives teacher's input, logs it,
    decides which student responds, checks if an event should fire or resolve,
    calls LLM to generate response, logs student response, and returns status.
    """
    from error_handler import SimulatorException, ErrorCategory, ErrorSeverity, RecoveryAction
    
    try:
        db_session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
        if not db_session:
            raise SimulatorException("Session not found", ErrorCategory.NETWORK, ErrorSeverity.CRITICAL, RecoveryAction.IGNORE)

        # 1. Log Teacher Message
        teacher_msg = SessionMessage(
            session_id=session_id,
            sender_type="teacher",
            sender_name="Teacher",
            message_text=turn_input.message,
        )
        db.add(teacher_msg)
        db.commit()

        # Get conversation history for LLM context
        history = db.query(SessionMessage).filter(SessionMessage.session_id == session_id).order_by(SessionMessage.timestamp.asc()).all()
        history_list = [
            {"sender_type": m.sender_type, "sender_name": m.sender_name, "message_text": m.message_text}
            for m in history
            if m.sender_type not in ["session_state", "state_checkpoint"]
        ]
        current_turn = len(history_list)

        # 2. Check for active events in recent history
        active_event_id = None
        system_messages = [m for m in history if m.sender_type == "system"]
        if system_messages:
            last_system_msg = system_messages[-1]
            event_resolved = False
            matching_events = [e for e in CLASSROOM_EVENTS if e["title"] in last_system_msg.sender_name]
            if matching_events:
                event_obj = matching_events[0]
                active_event_id = event_obj["id"]
                
                affected = [name.lower() for name in event_obj["affected_students"]]
                addressed = turn_input.addressed_student.lower() if turn_input.addressed_student else ""
                
                mentioned = any(name in turn_input.message.lower() for name in affected)
                is_action = turn_input.action in ["focus", "re-engage", "warn"] or addressed in affected
                
                if turn_input.action == "blackboard_share" and active_event_id in ["confusion", "attention_drop"]:
                    event_resolved = True
                    active_event_id = None
                elif mentioned or is_action:
                    event_resolved = True
                    active_event_id = None

        import json
        
        # 3. Retrieve previous noise and stress metrics from database
        last_state_msg = db.query(SessionMessage).filter(
            SessionMessage.session_id == session_id,
            SessionMessage.sender_type == "state_checkpoint"
        ).order_by(SessionMessage.timestamp.desc()).first()

        prev_noise = 30.0
        prev_stress = 20.0
        if last_state_msg:
            try:
                state_data = json.loads(last_state_msg.message_text)
                prev_noise = state_data.get("noise", 30.0)
                prev_stress = state_data.get("stress", 20.0)
            except Exception:
                pass
        else:
            # First turn: check scenario preset for initial values
            if db_session.scenario == "noisy":
                prev_noise = 75.0
                prev_stress = 50.0
            elif db_session.scenario == "hyperactive":
                prev_noise = 60.0
                prev_stress = 40.0

        # 4. Apply ECE turn evolution to student states and relationship coefficients
        all_student_states = db.query(StudentState).filter(
            StudentState.session_id == session_id
        ).all()
        
        # Evolve dynamics (returns current turn noise and stress)
        ece_metrics = evolve_states_and_relationships(
            student_states=all_student_states,
            teacher_message=turn_input.message,
            conversation_history=history_list,
            db=db
        )
        new_noise = ece_metrics["noise"]
        new_stress = ece_metrics["stress"]

        # 5. Compute classroom state for smart student selection
        classroom_state = compute_classroom_state(
            turn_number=current_turn,
            session_duration_minutes=db_session.duration_minutes or 15,
            student_states=all_student_states,
            noise=new_noise,
            stress=new_stress
        )

        # Save state checkpoint message to DB for tracking logs without migrations
        checkpoint_msg = SessionMessage(
            session_id=session_id,
            sender_type="state_checkpoint",
            sender_name="System",
            message_text=json.dumps({
                "noise": new_noise,
                "stress": new_stress,
                "attention": classroom_state["attention"],
                "confusion": classroom_state["confusion"],
                "curiosity": classroom_state["curiosity"],
                "energy": classroom_state["energy"],
                "engagement": classroom_state["engagement"]
            }, ensure_ascii=False)
        )
        db.add(checkpoint_msg)
        db.commit()

        # 6. Determine Responding Student(s) using personality-based probabilities
        is_interrupt = False
        if turn_input.action == "blackboard_share":
            responding_student_info = next((s for s in STUDENTS if s["name"] == "Riya"), STUDENTS[0])
        else:
            responders = select_responders(
                teacher_message=turn_input.message,
                addressed_student=turn_input.addressed_student,
                student_states=all_student_states,
                classroom_state=classroom_state,
                students_info=STUDENTS,
                conversation_history=history_list,
            )
            responding_student_info = responders[0]["info"] if responders else STUDENTS[0]
            if responders and responders[0]["reason"] == "interrupt":
                is_interrupt = True
        
        # 7. Determine if we should trigger a new random event (only if no event is currently active and not in demo mode)
        new_event_trigger = None
        if not active_event_id and not turn_input.is_demo:
            # Determine the last event from recent history to avoid consecutive duplicates
            last_event_id = None
            system_messages = [m for m in history if m.sender_type == "system"]
            if system_messages:
                last_system_msg = system_messages[-1]
                matching_events = [e for e in CLASSROOM_EVENTS if e["title"] in last_system_msg.sender_name]
                if matching_events:
                    last_event_id = matching_events[0]["id"]
            new_event_trigger = trigger_random_event(current_turn, classroom_state, last_event_id=last_event_id)
            if new_event_trigger:
                event_msg = SessionMessage(
                    session_id=session_id,
                    sender_type="system",
                    sender_name=f"Event: {new_event_trigger['title']}",
                    message_text=new_event_trigger["description"],
                )
                db.add(event_msg)
                db.commit()
                
                # Events override the responding student
                if new_event_trigger["id"] == "interruption":
                    responding_student_info = next((s for s in STUDENTS if s["name"] == "Ishaan"), responding_student_info)
                    is_interrupt = True
                elif new_event_trigger["id"] == "difficult_question":
                    responding_student_info = next((s for s in STUDENTS if s["name"] == "Aarav"), responding_student_info)
                elif new_event_trigger["id"] == "confusion":
                    responding_student_info = next((s for s in STUDENTS if s["name"] == "Riya"), responding_student_info)

        # 8. Generate Response Text via Personality-Driven AI or Demo Preset Bypass
        if turn_input.is_demo:
            print(f"[DEMO MODE] Bypassing LLM and TTS for message: {turn_input.message}")
            presets_path = os.path.join(backend_dir, "demo_presets.json")
            presets = []
            if os.path.exists(presets_path):
                try:
                    with open(presets_path, "r", encoding="utf-8") as f:
                        presets = json.load(f)
                except Exception as e:
                    print(f"[DEMO MODE Error] Failed to load presets: {e}")
            
            matched_preset = None
            t_msg_lower = turn_input.message.lower()
            for p in presets:
                if p["keywords"] == ["default"]:
                    continue
                if any(k in t_msg_lower for k in p["keywords"]):
                    matched_preset = p
                    break
            
            if not matched_preset:
                matched_preset = next((p for p in presets if p["keywords"] == ["default"]), {
                    "student": "Aarav",
                    "response_text": "Ah, I see! That makes sense, teacher. Can we write a small program to try this out?",
                    "emotion": "normal"
                })
                
            responding_student_info = next((s for s in STUDENTS if s["name"].lower() == matched_preset["student"].lower()), STUDENTS[0])
            student_reply = {
                "responding_student": responding_student_info["name"],
                "response_text": matched_preset["response_text"],
                "emotion": matched_preset["emotion"],
                "fallback_activated": False
            }
            
            # Update student state slightly for realism progress in demo mode
            student_name = responding_student_info["name"]
            state_rec = db.query(StudentState).filter(
                StudentState.session_id == session_id,
                StudentState.student_name == student_name
            ).first()
            if state_rec:
                state_rec.attention_level = max(0, min(100, state_rec.attention_level + 5))
                state_rec.understanding_level = max(0, min(100, state_rec.understanding_level + 10))
                state_rec.confusion_level = max(0, min(100, state_rec.confusion_level - 10))
                state_rec.participation_count += 1
                db.commit()
            
            # Warm the cache in background
            try:
                await generate_speech_audio(student_reply["response_text"], student_reply["responding_student"], db_session.language)
            except Exception as e:
                print(f"[DEMO MODE] Cache warming failed: {e}")
        else:
            print(f"[TURN] Session {session_id} | Turn {current_turn} | Student: {responding_student_info['name']} | Energy: {classroom_state['energy']}")
            student_reply = await generate_student_reply(
                session_id=session_id,
                db=db,
                subject=db_session.subject,
                topic=db_session.topic,
                class_level=db_session.class_level,
                objectives=db_session.lesson_objectives or "",
                method=db_session.teaching_method or "",
                language=db_session.language,
                student_name=responding_student_info["name"],
                student_personality=responding_student_info["personality"],
                teacher_message=turn_input.message,
                conversation_history=history_list,
                active_event=active_event_id or (new_event_trigger["id"] if new_event_trigger else None),
                is_interrupt=is_interrupt
            )

        # 9. Save Student Response to DB
        student_msg = SessionMessage(
            session_id=session_id,
            sender_type="student",
            sender_name=responding_student_info["name"],
            message_text=student_reply["response_text"],
            student_personality=responding_student_info.get("personality", "Curious student"),
        )
        db.add(student_msg)
        db.commit()

        # Save session state checkpoint message to DB for refresh-proof recovery
        final_active_event_id = active_event_id if not new_event_trigger else new_event_trigger["id"]
        state_payload = {
            "active_event_id": final_active_event_id,
            "responder_queue": turn_input.responder_queue or [],
            "elapsed_ratio": turn_input.elapsed_ratio or 0.0
        }
        state_msg = SessionMessage(
            session_id=session_id,
            sender_type="session_state",
            sender_name="SystemState",
            message_text=json.dumps(state_payload, ensure_ascii=False)
        )
        db.add(state_msg)
        db.commit()

        # Fetch updated student states to return to frontend
        updated_states = db.query(StudentState).filter(StudentState.session_id == session_id).all()
        student_states_serialized = [
            {
                "student_name": s.student_name,
                "attention_level": s.attention_level,
                "confidence_level": s.confidence_level,
                "understanding_level": s.understanding_level,
                "confusion_level": s.confusion_level,
                "memory_summary": s.memory_summary,
                "memory_size_bytes": len(s.memory_json) if s.memory_json else 0,
                "participation_count": s.participation_count
            }
            for s in updated_states
        ]

        return {
            "student_message": {
                "sender_name": responding_student_info["name"],
                "sender_type": "student",
                "message_text": student_reply["response_text"],
                "student_personality": responding_student_info.get("personality", "Curious student"),
                "emotion": student_reply["emotion"]
            },
            "fallback_activated": student_reply.get("fallback_activated", False),
            "triggered_event": new_event_trigger,
            "active_event_id": final_active_event_id,
            "student_states": student_states_serialized,
            "classroom_state": {
                "noise": new_noise,
                "stress": new_stress,
                "attention": classroom_state["attention"],
                "confusion": classroom_state["confusion"],
                "curiosity": classroom_state["curiosity"],
                "energy": classroom_state["energy"],
                "engagement": classroom_state["engagement"]
            }
        }
    except SimulatorException as sim_err:
        raise HTTPException(status_code=500, detail=sim_err.to_dict())
    except Exception as e:
        import traceback
        traceback.print_exc()
        err = SimulatorException(
            message=f"Internal simulator error: {str(e)}",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            recovery_action=RecoveryAction.IGNORE
        )
        raise HTTPException(status_code=500, detail=err.to_dict())


@app.post("/api/sessions/{session_id}/end", response_model=SessionAnalyticsOut)
async def end_session(session_id: int, db: Session = Depends(get_db)):
    """Ends the session, runs LLM performance appraisal on transcript, and saves analytics"""
    db_session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if analytics already exists
    existing_analytics = db.query(SessionAnalytics).filter(SessionAnalytics.session_id == session_id).first()
    if existing_analytics:
        return existing_analytics

    # Get entire session messages
    messages = db.query(SessionMessage).filter(SessionMessage.session_id == session_id).order_by(SessionMessage.timestamp.asc()).all()
    transcript = [
        {
            "sender_type": m.sender_type,
            "sender_name": m.sender_name,
            "message_text": m.message_text,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None
        }
        for m in messages
    ]

    if not transcript:
        raise HTTPException(status_code=400, detail="Cannot analyze an empty session.")

    # Get student states for evidence-based evaluation
    eval_student_states = db.query(StudentState).filter(
        StudentState.session_id == session_id
    ).all()

    # Call LLM evaluation with real metrics
    eval_result = await generate_evaluation(
        subject=db_session.subject,
        topic=db_session.topic,
        class_level=db_session.class_level,
        objectives=db_session.lesson_objectives or "",
        method=db_session.teaching_method or "",
        language=db_session.language,
        transcript=transcript,
        student_states=eval_student_states,
    )

    db_analytics = SessionAnalytics(
        session_id=session_id,
        communication_score=eval_result["communication_score"],
        engagement_score=eval_result["engagement_score"],
        time_management_score=eval_result["time_management_score"],
        question_handling_score=eval_result["question_handling_score"],
        suggestions=eval_result["suggestions"],
        transcript_summary=eval_result["transcript_summary"]
    )
    db.add(db_analytics)
    db.commit()
    db.refresh(db_analytics)
    
    # Auto-generate and save the final_project_report.md to workspace root
    try:
        get_session_report(session_id, db)
    except Exception as report_err:
        print(f"[REPORT Error] Auto-generating report on end failed: {report_err}")
        
    return db_analytics


@app.get("/api/sessions/{session_id}/analytics", response_model=SessionAnalyticsOut)
def get_session_analytics(session_id: int, db: Session = Depends(get_db)):
    """Retrieves computed B.Ed training analytics for a session"""
    analytics = db.query(SessionAnalytics).filter(SessionAnalytics.session_id == session_id).first()
    if not analytics:
        raise HTTPException(status_code=404, detail="Analytics not found. Call /api/sessions/{id}/end first.")
    return analytics


@app.get("/api/sessions/{session_id}/report")
def get_session_report(session_id: int, db: Session = Depends(get_db)):
    """Generates the comprehensive pedagogical report in Markdown format for SkillX and Mentors"""
    db_session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    analytics = db.query(SessionAnalytics).filter(SessionAnalytics.session_id == session_id).first()
    if not analytics:
        raise HTTPException(status_code=404, detail="Analytics report not generated yet. Call session /end first.")

    turns_count = db.query(SessionMessage).filter(
        SessionMessage.session_id == session_id,
        SessionMessage.sender_type != "session_state",
        SessionMessage.sender_type != "state_checkpoint"
    ).count()

    avg_score = round((analytics.communication_score + analytics.engagement_score + analytics.time_management_score + analytics.question_handling_score) / 4.0, 1)

    report_md = f"""# 🔬 Future Classroom Simulator: B.Ed Pedagogical Assessment Report

This professional evaluation report compiles classroom metadata, telemetry statistics, student dynamic indicators, and pedagogical training evaluations. Prepared for the **SkillX Public Demonstration and Mentor Review**.

---

## 1. Classroom Session Metadata
- **Session ID**: {session_id}
- **Subject**: {db_session.subject}
- **Topic**: {db_session.topic}
- **Grade Level**: {db_session.class_level}
- **Scenario Preset**: {db_session.scenario.replace('_', ' ').title()}
- **Teaching Method**: {db_session.teaching_method}
- **Duration**: {db_session.duration_minutes} minutes (Actual: {turns_count} turns executed)
- **Instructional Language**: {db_session.language}
- **Evaluation Date**: {datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")}

---

## 2. Pedagogical Assessment Scores
| Evaluation Category | Score achieved | Benchmark (Passing: 70) | Status |
| :--- | :--- | :--- | :--- |
| **Communication Skills** | {analytics.communication_score} / 100 | 70 | {"✅ Passed" if analytics.communication_score >= 70 else "⚠️ Needs Review"} |
| **Classroom Engagement** | {analytics.engagement_score} / 100 | 70 | {"✅ Passed" if analytics.engagement_score >= 70 else "⚠️ Needs Review"} |
| **Pacing & Time Management** | {analytics.time_management_score} / 100 | 70 | {"✅ Passed" if analytics.time_management_score >= 70 else "⚠️ Needs Review"} |
| **Question Handling & Scaffolding** | {analytics.question_handling_score} / 100 | 70 | {"✅ Passed" if analytics.question_handling_score >= 70 else "⚠️ Needs Review"} |
| **Overall Performance Average** | **{avg_score} / 100** | **70** | **{"🎉 Competent" if avg_score >= 80 else "✅ Passed" if avg_score >= 70 else "⚠️ Intervention Required"}** |

---

## 3. Session Transcript Summary
{analytics.transcript_summary}

---

## 4. B.Ed Assessor Appraisals & Suggestions
{analytics.suggestions}

---

## 5. Subsystems Architecture & Innovation Points
1. **Emergent Classroom Engine (ECE)**
   - Simulates turn-taking dynamics where student reactions emerge from individual metrics (Attention, Confidence, Understanding, Confusion) and classroom-level metrics (Noise, Stress).
2. **Speech Synthesis (TTS) & STT Cascade**
   - High-fidelity Microsoft Edge Neural TTS voices adjusted per personality. Dual-channel STT WebSocket handles binary Opus audio streams with low-latency interim drafting.
3. **Simulation Validation & Self-Healing**
   - Jaccard repetition validation caps student volunteer counts, handles silence triggers, and clamps impossible state deviations dynamically.

---

## 6. Limitations & Future Scope
- **Limitations**: Requires API connectivity for full LLM features. Autoplay browser restrictions block audio play until direct user page click.
- **Future Scope**: Multi-agent student-to-student conversations, integration with VR platforms, and automated lesson-plan parsing.
"""
    
    # Save the report directly to the workspace as final_project_report.md
    try:
        workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        report_path = os.path.join(workspace_dir, "final_project_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"[REPORT] Successfully wrote report file to: {report_path}")
    except Exception as e:
        print(f"[REPORT Error] Failed to write report file: {e}")

    return {"report_md": report_md}


@app.get("/api/tts")
async def text_to_speech(text: str, student: str, language: str = "English"):
    """
    Synthesizes and streams the spoken audio file for the student and text.
    Uses Edge TTS for natural human-like neural voices.
    """
    if not text.strip() or not student.strip():
        raise HTTPException(status_code=400, detail="Missing required 'text' or 'student' query parameters.")
    try:
        # Await the fully async in-memory byte synthesis
        audio_bytes, is_cache_hit = await generate_speech_audio(text, student, language)
        
        # Stream response directly from memory using BytesIO and StreamingResponse
        from io import BytesIO
        from fastapi.responses import StreamingResponse
        
        return StreamingResponse(
            BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(audio_bytes)),
                "X-Cache": "HIT" if is_cache_hit else "MISS"
            }
        )
    except Exception as e:
        print(f"TTS API Endpoint Error: {e}")
        from error_handler import SimulatorException, ErrorCategory, ErrorSeverity, RecoveryAction
        err = SimulatorException(
            message=f"TTS synthesis failed: {str(e)}",
            category=ErrorCategory.SPEECH,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=RecoveryAction.IGNORE
        )
        raise HTTPException(status_code=500, detail=err.to_dict())


def transcribe_google(audio_content: bytes, mime_type: str = "audio/webm") -> dict:
    import sys
    import json
    from google.oauth2 import service_account
    from google.cloud import speech
    
    # Load credentials from JSON environment string if present (for production hosting compatibility)
    json_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if json_creds:
        try:
            info = json.loads(json_creds)
            credentials = service_account.Credentials.from_service_account_info(info)
            client = speech.SpeechClient(credentials=credentials)
            print("[Google STT] Successfully loaded SpeechClient with credentials from JSON environment variable.")
        except Exception as cred_err:
            print(f"[Google STT Error] Failed to load credentials from JSON env: {cred_err}. Falling back to default credentials.")
            client = speech.SpeechClient()
    else:
        client = speech.SpeechClient()
        
    audio = speech.RecognitionAudio(content=audio_content)
    
    # Determine encoding based on MIME type (Omit hardcoded sample rates to let Google STT auto-detect)
    if "webm" in mime_type:
        encoding = speech.RecognitionConfig.AudioEncoding.WEBM_OPUS
    elif "ogg" in mime_type or "opus" in mime_type:
        encoding = speech.RecognitionConfig.AudioEncoding.OGG_OPUS
    else:
        encoding = speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED
        
    config = speech.RecognitionConfig(
        encoding=encoding,
        language_code="en-IN",
        alternative_language_codes=["hi-IN", "bn-IN"],
        enable_automatic_punctuation=True,
        use_enhanced=True,
        model="latest_short"
    )
    response = client.recognize(config=config, audio=audio)
    transcript = ""
    confidence = 1.0
    confidences = []
    
    for result in response.results:
        transcript += result.alternatives[0].transcript
        confidences.append(result.alternatives[0].confidence)
        
    if confidences:
        confidence = sum(confidences) / len(confidences)
        
    return {"text": transcript, "confidence": confidence}


async def transcribe_deepgram(audio_content: bytes) -> dict:
    import httpx
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY not set")
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/webm"
    }
    params = {
        "model": "nova-2",
        "smart_format": "true",
        "detect_language": "true"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            params=params,
            content=audio_content,
            timeout=30.0
        )
        if response.status_code == 200:
            res_json = response.json()
            alt = res_json["results"]["channels"][0]["alternatives"][0]
            return {"text": alt["transcript"], "confidence": alt["confidence"]}
        else:
            raise Exception(f"Deepgram STT failed: {response.text}")


async def transcribe_assemblyai(audio_content: bytes) -> dict:
    import httpx
    import asyncio
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not set")
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    upload_headers = {
        "Authorization": api_key,
        "Content-Type": "application/octet-stream"
    }
    async with httpx.AsyncClient() as client:
        upload_resp = await client.post(
            "https://api.assemblyai.com/v2/upload",
            headers=upload_headers,
            content=audio_content,
            timeout=60.0
        )
        if upload_resp.status_code != 200:
            raise Exception(f"AssemblyAI upload failed: {upload_resp.text}")
        audio_url = upload_resp.json()["upload_url"]
        
        transcribe_resp = await client.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers,
            json={
                "audio_url": audio_url,
                "language_detection": True
            }
        )
        if transcribe_resp.status_code != 200:
            raise Exception(f"AssemblyAI transcription trigger failed: {transcribe_resp.text}")
        transcript_id = transcribe_resp.json()["id"]
        
        for _ in range(30):
            await asyncio.sleep(1.0)
            poll_resp = await client.get(
                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                headers=headers
            )
            if poll_resp.status_code == 200:
                res_json = poll_resp.json()
                status = res_json["status"]
                if status == "completed":
                    return {"text": res_json["text"], "confidence": res_json.get("confidence", 1.0)}
                elif status == "error":
                    raise Exception(f"AssemblyAI failed: {res_json.get('error')}")
        raise Exception("AssemblyAI transcription timed out")


from fastapi import Header

async def perform_stt_cascade(audio_content: bytes, mime_type: str) -> dict:
    """
    Unified Speech-to-Text provider cascade with fallback and confidence filtering.
    """
    errors = []
    
    # 0. Gemini Speech-to-Text (Primary) — using new google.genai SDK
    if os.environ.get("GEMINI_API_KEY"):
        try:
            print("[STT-Cascade] Attempting Gemini Speech-to-Text (google.genai SDK)...")
            from google import genai as google_genai
            import base64
            stt_client = google_genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            audio_b64 = base64.standard_b64encode(audio_content).decode("utf-8")
            response = stt_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": audio_b64
                                }
                            },
                            {
                                "text": "Transcribe this audio. Output only the exact transcribed text, with no extra annotations, prefixes, or commentary. If the audio is empty or contains only noise/silence, output an empty string."
                            }
                        ]
                    }
                ]
            )
            result = response.text.strip() if response.text else ""
            if result:
                print(f"[STT-Cascade] Gemini STT Success: '{result}'")
                return {"text": result, "provider": "gemini", "confidence": 1.0, "low_confidence": False}
        except Exception as e:
            err_msg = f"Gemini STT Error: {e}"
            print(f"[STT-Cascade] {err_msg}")
            errors.append(err_msg)

    # 1. Google Speech-to-Text (Secondary)
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GOOGLE_API_KEY"):
        try:
            print("[STT-Cascade] Attempting Google Cloud Speech-to-Text...")
            import concurrent.futures
            import asyncio
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                res_dict = await loop.run_in_executor(pool, transcribe_google, audio_content, mime_type)
                if res_dict and res_dict.get("text"):
                    text = res_dict["text"]
                    confidence = res_dict.get("confidence", 1.0)
                    low_conf = confidence < 0.65
                    print(f"[STT-Cascade] Google STT Success: '{text}' (confidence: {confidence:.2f})")
                    return {
                        "text": text if not low_conf else "I couldn't clearly hear that. Could you repeat?",
                        "provider": "google",
                        "confidence": confidence,
                        "low_confidence": low_conf
                    }
        except Exception as e:
            err_msg = f"Google STT Error: {e}"
            print(f"[STT-Cascade] {err_msg}")
            errors.append(err_msg)

    # 2. Deepgram (Secondary)
    if os.environ.get("DEEPGRAM_API_KEY"):
        try:
            print("[STT-Cascade] Attempting Deepgram Nova-2...")
            res_dict = await transcribe_deepgram(audio_content)
            if res_dict and res_dict.get("text"):
                text = res_dict["text"]
                confidence = res_dict.get("confidence", 1.0)
                low_conf = confidence < 0.65
                print(f"[STT-Cascade] Deepgram Success: '{text}' (confidence: {confidence:.2f})")
                return {
                    "text": text if not low_conf else "I couldn't clearly hear that. Could you repeat?",
                    "provider": "deepgram",
                    "confidence": confidence,
                    "low_confidence": low_conf
                }
        except Exception as e:
            err_msg = f"Deepgram Error: {e}"
            print(f"[STT-Cascade] {err_msg}")
            errors.append(err_msg)

    # 3. AssemblyAI (Tertiary)
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        try:
            print("[STT-Cascade] Attempting AssemblyAI...")
            res_dict = await transcribe_assemblyai(audio_content)
            if res_dict and res_dict.get("text"):
                text = res_dict["text"]
                confidence = res_dict.get("confidence", 1.0)
                low_conf = confidence < 0.65
                print(f"[STT-Cascade] AssemblyAI Success: '{text}' (confidence: {confidence:.2f})")
                return {
                    "text": text if not low_conf else "I couldn't clearly hear that. Could you repeat?",
                    "provider": "assemblyai",
                    "confidence": confidence,
                    "low_confidence": low_conf
                }
        except Exception as e:
            err_msg = f"AssemblyAI Error: {e}"
            print(f"[STT-Cascade] {err_msg}")
            errors.append(err_msg)

    # If all failed or no keys are configured:
    from error_handler import SimulatorException, ErrorCategory, ErrorSeverity, RecoveryAction
    err = SimulatorException(
        message=f"Speech-to-Text cascade failed completely. Errors: {errors}",
        category=ErrorCategory.SPEECH,
        severity=ErrorSeverity.HIGH,
        recovery_action=RecoveryAction.MANUAL_INPUT
    )
    raise HTTPException(
        status_code=500,
        detail=err.to_dict()
    )


@app.post("/api/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...),
    x_audio_mime_type: Optional[str] = Header(None)
):
    """
    REST Endpoint: Receives an audio file from the teacher microphone and transcribes it to text
    via unified Speech-to-Text provider cascade.
    """
    audio_content = await file.read()
    if not audio_content:
        raise HTTPException(status_code=400, detail="Empty audio file uploaded")
    
    mime_type = x_audio_mime_type or file.content_type or "audio/webm"
    print(f"[STT REST] Dynamic audio mime-type: {mime_type} ({len(audio_content)} bytes)")
    
    return await perform_stt_cascade(audio_content, mime_type)


@app.websocket("/api/stream-stt")
async def stream_stt(websocket: WebSocket):
    """
    WebSocket Endpoint: Accepts real-time binary audio stream chunks (Opus/WebM) from teacher microphone,
    provides dynamic real-time partial/interim transcription updates, and delivers final high-accuracy
    transcriptions upon client speech completion.
    """
    await websocket.accept()
    print("[WS-STT] Client microphone stream connected successfully.")
    
    audio_buffer = bytearray()
    mime_type = "audio/webm"
    chunk_counter = 0
    
    try:
        while True:
            # Block waiting for either text stop command or binary audio chunk
            message = await websocket.receive()
            
            if "bytes" in message:
                chunk = message["bytes"]
                if chunk:
                    audio_buffer.extend(chunk)
                    chunk_counter += 1
                    
                    # Generate dynamic interim partial transcription updates every 4 chunks (~1s)
                    # to keep the interface highly responsive and conversational
                    if chunk_counter % 4 == 0 and len(audio_buffer) > 15000:
                        try:
                            # Run cascade in background to fetch fast draft text
                            # We enforce a short timeout to prevent blocking the socket thread
                            import asyncio
                            draft_res = await asyncio.wait_for(
                                perform_stt_cascade(bytes(audio_buffer), mime_type),
                                timeout=1.5
                            )
                            draft_text = draft_res.get("text", "")
                            
                            # Filter filler system/retry warnings from interim text
                            if draft_text and not draft_res.get("low_confidence"):
                                await websocket.send_json({
                                    "text": draft_text,
                                    "is_final": False
                                })
                        except Exception:
                            # Fail silently for interim updates to avoid socket crashes
                            pass
                            
            elif "text" in message:
                command = message["text"]
                if command == "STOP":
                    print(f"[WS-STT] Client requested STOP transcription. Total buffer size: {len(audio_buffer)} bytes.")
                    break
                    
    except WebSocketDisconnect:
        print("[WS-STT] Microphone WebSocket disconnected by client.")
    except Exception as e:
        print(f"[WS-STT Error] Stream error: {e}")
        
    # Deliver the definitive final transcription result
    if len(audio_buffer) > 4000:
        try:
            print(f"[WS-STT] Compiling and generating definitive final transcription cascade...")
            final_res = await perform_stt_cascade(bytes(audio_buffer), mime_type)
            await websocket.send_json({
                "text": final_res.get("text", ""),
                "is_final": True,
                "low_confidence": final_res.get("low_confidence", False),
                "provider": final_res.get("provider", "google")
            })
        except Exception as e:
            print(f"[WS-STT Error] Final transcription cascade failed: {e}")
            await websocket.send_json({
                "text": "I couldn't clearly hear that. Could you repeat?",
                "is_final": True,
                "low_confidence": True,
                "error": str(e)
            })
    else:
        # Buffer is too small (e.g. mic click with no speech)
        await websocket.send_json({
            "text": "",
            "is_final": True
        })
@app.get("/api/config")
async def get_config():
    """
    Returns configuration status, such as whether speech-to-text API keys are configured.
    """
    has_keys = bool(
        os.environ.get("GEMINI_API_KEY") or
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or
        os.environ.get("GOOGLE_API_KEY") or
        os.environ.get("DEEPGRAM_API_KEY") or
        os.environ.get("ASSEMBLYAI_API_KEY")
    )
    return {"has_stt_keys": has_keys}

@app.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Runs diagnostic checks on backend services:
    - Gemini API Key presence
    - Database connection health
    - Audio cache write permissions
    - TTS synthesis ping (checks edge_tts communicating loop)
    """
    import os
    from database import engine
    from sqlalchemy import text
    from voice import TTS_CACHE
    
    # 1. API Key Check
    gemini_key = os.environ.get("GEMINI_API_KEY")
    api_key_valid = bool(gemini_key and len(gemini_key.strip()) > 5)
    
    # 2. Database Connection Check
    db_ok = False
    db_msg = ""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
        db_msg = f"Database connected successfully ({engine.url.drivername})"
    except Exception as e:
        db_msg = str(e)
        
    # 3. In-Memory Cache Check
    cache_ok = False
    cache_msg = ""
    try:
        TTS_CACHE.set("__health_check_temp__", b"1")
        val = TTS_CACHE.get("__health_check_temp__")
        if val == b"1":
            cache_ok = True
            cache_msg = "In-memory TTS cache read/write functional"
    except Exception as e:
        cache_msg = str(e)
        
    # 4. Edge TTS Reachability Check
    tts_ok = False
    tts_msg = ""
    try:
        import edge_tts
        # Run a real synthesis test to verify connection to Edge TTS servers
        communicate = edge_tts.Communicate("OK", "en-IN-PrabhatNeural")
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
        if len(audio_data) > 0:
            tts_ok = True
            tts_msg = "Edge TTS engine verified (successful synthesis)"
        else:
            tts_msg = "Edge TTS generated empty audio data"
    except Exception as e:
        tts_msg = str(e)
        
    # 5. STT Service check
    stt_ok = False
    stt_msg = ""
    try:
        from google.cloud import speech
        has_stt_creds = bool(
            os.environ.get("GEMINI_API_KEY") or
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or
            os.environ.get("GOOGLE_CREDENTIALS_JSON") or
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON") or
            os.environ.get("DEEPGRAM_API_KEY") or
            os.environ.get("ASSEMBLYAI_API_KEY")
        )
        if has_stt_creds:
            stt_ok = True
            stt_msg = "STT Cascade active (at least one API provider configured)"
        else:
            stt_msg = "STT Offline (No Gemini, Google, Deepgram, or AssemblyAI API keys set)"
    except Exception as e:
        stt_msg = str(e)

    # 6. Schema Check
    schema_ok, schema_msg = check_db_schema_valid()

    overall_passed = api_key_valid and db_ok and cache_ok and tts_ok and stt_ok and schema_ok
    
    return {
        "status": "passed" if overall_passed else "failed",
        "api_key_valid": api_key_valid,
        "database_connected": db_ok,
        "database_message": db_msg,
        "database_schema_valid": schema_ok,
        "database_schema_message": schema_msg,
        "cache_writable": cache_ok,
        "cache_message": cache_msg,
        "tts_available": tts_ok,
        "tts_message": tts_msg,
        "stt_available": stt_ok,
        "stt_message": stt_msg
    }


def check_db_schema_valid() -> tuple[bool, str]:
    try:
        from database import engine
        from sqlalchemy import inspect
        inspector = inspect(engine)
        
        # Define the exact required tables and columns we want to validate, matching models.py
        required_schema = {
            "sessions": [
                "id", "subject", "topic", "class_level", "lesson_objectives", 
                "teaching_method", "duration_minutes", "language", "scenario", "created_at"
            ],
            "student_states": [
                "id", "session_id", "student_name", "attention_level", "confidence_level", 
                "understanding_level", "confusion_level", "curiosity_level", "interrupt_probability", 
                "memory_summary", "memory_json", "participation_count"
            ],
            "session_messages": [
                "id", "session_id", "sender_type", "sender_name", "message_text", 
                "student_personality", "timestamp"
            ],
            "session_analytics": [
                "id", "session_id", "communication_score", "engagement_score", 
                "time_management_score", "question_handling_score", "suggestions", "transcript_summary"
            ]
        }
        
        for table, columns in required_schema.items():
            if not inspector.has_table(table):
                return False, f"Missing table '{table}'"
            
            existing_cols = {col["name"] for col in inspector.get_columns(table)}
            for req_col in columns:
                if req_col not in existing_cols:
                    return False, f"Missing column '{req_col}' in table '{table}'"
                    
        return True, "VALID"
    except Exception as e:
        return False, f"Validation error: {e}"


@app.on_event("startup")
async def run_startup_self_test():
    print("====================================================")
    print("🚀 Future Classroom Simulator Startup Self-Test")
    print("====================================================")
    
    # 1. Production Mode Check & Database Url requirements
    is_prod = (
        os.environ.get("RENDER") == "true" or
        bool(os.environ.get("RAILWAY_STATIC_URL")) or
        os.environ.get("NODE_ENV") == "production"
    )
    
    db_url = os.environ.get("DATABASE_URL")
    if is_prod and (not db_url or db_url.startswith("sqlite")):
        print("❌ CRITICAL: Production environment detected but database is missing or configured as SQLite.")
        print("DATABASE_URL must be set to a valid PostgreSQL connection string in production.")
        raise RuntimeError("PostgreSQL database is required in production deployment contexts.")

    # 2. Gemini Key Check
    gemini_key = os.environ.get("GEMINI_API_KEY")
    api_key_valid = bool(gemini_key and len(gemini_key.strip()) > 5)
    
    gemini_client_initialized = False
    gemini_model_verified = False
    
    if api_key_valid:
        try:
            from google import genai as google_genai
            client = google_genai.Client(api_key=gemini_key)
            gemini_client_initialized = True
            
            # Fast model availability connectivity check
            import concurrent.futures
            import asyncio
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        pool,
                        lambda: client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents="Ping"
                        )
                    ),
                    timeout=3.5
                )
            if response and response.text:
                gemini_model_verified = True
        except Exception as e:
            print(f"[Gemini Check] Warning: Model connectivity check failed: {e}")
            
    print(f"Gemini API Key: {'✅ CONFIGURED' if api_key_valid else '❌ MISSING'}")
    
    # 3. Database Connection Check
    db_status = "❌ UNKNOWN"
    db_type = "unknown"
    try:
        from database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_type = engine.url.drivername
        db_status = f"✅ CONNECTED ({db_type})"
    except Exception as e:
        db_status = f"❌ CONNECTION FAILED: {e}"
    print(f"Database: {db_status}")
    
    # 4. Database Schema Validation
    schema_ok, schema_msg = check_db_schema_valid()
    print(f"Database Schema: {'✅ VALID' if schema_ok else '❌ INVALID (' + schema_msg + ')'}")
    
    # 5. Edge TTS Engine Check with outbound request validation
    tts_status = "❌ UNKNOWN"
    try:
        import edge_tts
        # Verify outbound network requests by synthesizing a very short text
        communicate = edge_tts.Communicate("OK", "en-IN-PrabhatNeural")
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
        if len(audio_data) > 0:
            tts_status = "✅ ACTIVE"
        else:
            tts_status = "❌ FAILED (Empty audio returned)"
    except Exception as e:
        tts_status = f"❌ OFFLINE ({e})"
    print(f"Edge TTS Engine: {tts_status}")
    
    # 6. STT Engine / Cascade Config with actual validation
    stt_providers = []
    
    # Check Google STT loading from JSON or file path
    google_stt_ok = False
    json_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    file_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if json_creds or file_creds:
        try:
            from google.cloud import speech
            if json_creds:
                import json
                from google.oauth2 import service_account
                info = json.loads(json_creds)
                credentials = service_account.Credentials.from_service_account_info(info)
                speech.SpeechClient(credentials=credentials)
            else:
                speech.SpeechClient()
            google_stt_ok = True
            stt_providers.append("Google STT")
        except Exception as e:
            print(f"[STT Check] Google STT init warning: {e}")
            
    if os.environ.get("GEMINI_API_KEY") and gemini_client_initialized:
        stt_providers.append("Gemini STT")
    if os.environ.get("DEEPGRAM_API_KEY"):
        stt_providers.append("Deepgram")
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        stt_providers.append("AssemblyAI")
        
    stt_status = "✅ ACTIVE" if stt_providers else "❌ OFFLINE"
    print(f"Speech-To-Text STT: {stt_status}")
    
    # 7. Websocket Readiness
    print("Websocket Interface: ✅ READY")
    print("====================================================")
    
    # Fail startup if key is missing and ALLOW_MOCK_LLM is not active
    allow_mock = os.environ.get("ALLOW_MOCK_LLM", "false").lower() == "true"
    if not api_key_valid and not allow_mock:
        print("❌ CRITICAL: GEMINI_API_KEY is not set. Startup aborted.")
        print("To run locally/mock mode without keys, set ALLOW_MOCK_LLM=true.")
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your environment variables.")



