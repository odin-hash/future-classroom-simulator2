import os
import sys

# Dynamically add the backend directory to sys.path to support imports from both root and subdirectories
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import random
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile
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
)
from fastapi.responses import FileResponse
from voice import generate_speech_audio

# Initialize database tables
try:
    Base.metadata.create_all(bind=engine)
except Exception as table_err:
    print(f"[DB] Metadata create_all warning: {table_err}")

# Auto-migrate: Ensure newly added columns exist in deployed database (e.g. Postgres on Render)
from sqlalchemy import text
try:
    with engine.begin() as conn:
        for table, col_name, col_type in [
            ("student_states", "curiosity_level", "INTEGER DEFAULT 50"),
            ("student_states", "interrupt_probability", "INTEGER DEFAULT 20"),
            ("student_states", "memory_json", "TEXT"),
            ("sessions", "language", "VARCHAR(50) DEFAULT 'English'"),
            ("sessions", "lesson_objectives", "TEXT"),
            ("sessions", "teaching_method", "VARCHAR(100)"),
            ("session_messages", "student_personality", "VARCHAR(100)"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                print(f"[DB] Added column {col_name} to {table}.")
            except Exception:
                # Column likely already exists or table doesn't exist yet
                pass
except Exception as db_err:
    print(f"[DB] Auto-migration helper warning: {db_err}")

app = FastAPI(title="Future Classroom Simulator API")

# Configure CORS for Vite Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local dev simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    db_session = ClassroomSession(
        subject=session_data.subject,
        topic=session_data.topic,
        class_level=session_data.class_level,
        lesson_objectives=session_data.lesson_objectives,
        teaching_method=session_data.teaching_method,
        duration_minutes=session_data.duration_minutes,
        language=session_data.language,
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    # Populate initial StudentState for each of the 6 students (using personality-driven defaults)
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
    db_session = db.query(ClassroomSession).filter(ClassroomSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")

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
    ]
    current_turn = len(history_list)

    # 2. Check for active events in recent history
    # If the last message was a system event that hasn't been addressed, it is active.
    active_event_id = None
    system_messages = [m for m in history if m.sender_type == "system"]
    if system_messages:
        # Check if teacher addressed this event in the latest turn
        # e.g., if there was a whispering event, did the teacher mention Vihaan/Ishaan or use a refocus action?
        last_system_msg = system_messages[-1]
        
        # Check if event was already resolved by looking if there are newer messages addressing it
        # In this simple model, let's look if the teacher addressed the affected students
        event_resolved = False
        
        # Determine which event it was
        matching_events = [e for e in CLASSROOM_EVENTS if e["title"] in last_system_msg.sender_name]
        if matching_events:
            event_obj = matching_events[0]
            active_event_id = event_obj["id"]
            
            # Resolution conditions:
            # - Teacher addressed the affected student(s)
            # - Teacher action is provided (like "focus" or "warn")
            # - Teacher mentions the affected student's name
            affected = [name.lower() for name in event_obj["affected_students"]]
            addressed = turn_input.addressed_student.lower() if turn_input.addressed_student else ""
            
            mentioned = any(name in turn_input.message.lower() for name in affected)
            is_action = turn_input.action in ["focus", "re-engage", "warn"] or addressed in affected
            
            if turn_input.action == "blackboard_share" and active_event_id in ["confusion", "attention_drop"]:
                event_resolved = True
                active_event_id = None
            elif mentioned or is_action:
                event_resolved = True
                active_event_id = None  # event is now cleared!

    # 3. Apply attention decay to all students each turn
    all_student_states = db.query(StudentState).filter(
        StudentState.session_id == session_id
    ).all()
    apply_attention_decay(all_student_states, current_turn, db)

    # 4. Compute classroom state for smart student selection
    classroom_state = compute_classroom_state(
        turn_number=current_turn,
        session_duration_minutes=db_session.duration_minutes or 15,
        student_states=all_student_states,
    )

    # 5. Determine Responding Student(s) using personality-based probabilities
    if turn_input.action == "blackboard_share":
        responding_student_info = next((s for s in STUDENTS if s["name"] == "Riya"), STUDENTS[0])
    else:
        responders = select_responders(
            teacher_message=turn_input.message,
            addressed_student=turn_input.addressed_student,
            student_states=all_student_states,
            classroom_state=classroom_state,
            students_info=STUDENTS,
        )
        responding_student_info = responders[0]["info"] if responders else STUDENTS[0]
    
    # 6. Determine if we should trigger a new random event (only if no event is currently active)
    new_event_trigger = None
    if not active_event_id:
        new_event_trigger = trigger_random_event(current_turn)
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
            elif new_event_trigger["id"] == "difficult_question":
                responding_student_info = next((s for s in STUDENTS if s["name"] == "Aarav"), responding_student_info)
            elif new_event_trigger["id"] == "confusion":
                responding_student_info = next((s for s in STUDENTS if s["name"] == "Riya"), responding_student_info)

    # 7. Generate Response Text via Personality-Driven AI
    print(f"[TURN] Session {session_id} | Turn {current_turn} | Student: {responding_student_info['name']} | Energy: {classroom_state['energy_level']}")
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
        active_event=active_event_id or (new_event_trigger["id"] if new_event_trigger else None)
    )

    # 6. Save Student Response to DB
    student_msg = SessionMessage(
        session_id=session_id,
        sender_type="student",
        sender_name=responding_student_info["name"],
        message_text=student_reply["response_text"],
        student_personality=responding_student_info["personality"],
    )
    db.add(student_msg)
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
            "participation_count": s.participation_count
        }
        for s in updated_states
    ]

    return {
        "student_message": {
            "sender_name": responding_student_info["name"],
            "sender_type": "student",
            "message_text": student_reply["response_text"],
            "student_personality": responding_student_info["personality"],
            "emotion": student_reply["emotion"]
        },
        "triggered_event": new_event_trigger,
        "active_event_id": active_event_id if not new_event_trigger else new_event_trigger["id"],
        "student_states": student_states_serialized
    }


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
        {"sender_type": m.sender_type, "sender_name": m.sender_name, "message_text": m.message_text}
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
    return db_analytics


@app.get("/api/sessions/{session_id}/analytics", response_model=SessionAnalyticsOut)
def get_session_analytics(session_id: int, db: Session = Depends(get_db)):
    """Retrieves computed B.Ed training analytics for a session"""
    analytics = db.query(SessionAnalytics).filter(SessionAnalytics.session_id == session_id).first()
    if not analytics:
        raise HTTPException(status_code=404, detail="Analytics not found. Call /api/sessions/{id}/end first.")
    return analytics


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
        audio_bytes = await generate_speech_audio(text, student, language)
        
        # Stream response directly from memory using BytesIO and StreamingResponse
        from io import BytesIO
        from fastapi.responses import StreamingResponse
        
        return StreamingResponse(
            BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(audio_bytes))
            }
        )
    except Exception as e:
        print(f"TTS API Endpoint Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def transcribe_google(audio_content: bytes, mime_type: str = "audio/webm") -> str:
    import sys
    from google.cloud import speech
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
        model="latest_long"
    )
    response = client.recognize(config=config, audio=audio)
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript
    return transcript


async def transcribe_deepgram(audio_content: bytes) -> str:
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
            return res_json["results"]["channels"][0]["alternatives"][0]["transcript"]
        else:
            raise Exception(f"Deepgram STT failed: {response.text}")


async def transcribe_assemblyai(audio_content: bytes) -> str:
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
                status = poll_resp.json()["status"]
                if status == "completed":
                    return poll_resp.json()["text"]
                elif status == "error":
                    raise Exception(f"AssemblyAI failed: {poll_resp.json().get('error')}")
        raise Exception("AssemblyAI transcription timed out")


from fastapi import Header

@app.post("/api/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...),
    x_audio_mime_type: Optional[str] = Header(None)
):
    """
    Receives an audio file from the teacher microphone and transcribes it to text.
    Dispatches to Google STT, Deepgram, or AssemblyAI with fallback.
    """
    import asyncio
    audio_content = await file.read()
    if not audio_content:
        raise HTTPException(status_code=400, detail="Empty audio file uploaded")
    
    errors = []
    mime_type = x_audio_mime_type or file.content_type or "audio/webm"
    print(f"[STT] Dynamic audio mime-type: {mime_type}")
    
    # 0. Gemini Speech-to-Text (Primary) — using new google.genai SDK
    if os.environ.get("GEMINI_API_KEY"):
        try:
            print("[STT] Attempting Gemini Speech-to-Text (google.genai SDK)...")
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
            result = response.text.strip()
            if result:
                print(f"[STT] Gemini STT Success: '{result}'")
                return {"text": result, "provider": "gemini"}
        except Exception as e:
            err_msg = f"Gemini STT Error: {e}"
            print(f"[STT] {err_msg}")
            errors.append(err_msg)
            
    # 1. Google Speech-to-Text (Secondary)
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GOOGLE_API_KEY"):
        try:
            print("[STT] Attempting Google Cloud Speech-to-Text...")
            import concurrent.futures
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(pool, transcribe_google, audio_content, mime_type)
                if result:
                    print(f"[STT] Google Cloud STT Success: '{result}'")
                    return {"text": result, "provider": "google"}
        except Exception as e:
            err_msg = f"Google STT Error: {e}"
            print(f"[STT] {err_msg}")
            errors.append(err_msg)
            
    # 2. Deepgram (Secondary)
    if os.environ.get("DEEPGRAM_API_KEY"):
        try:
            print("[STT] Attempting Deepgram Nova-2...")
            result = await transcribe_deepgram(audio_content)
            if result:
                print(f"[STT] Deepgram Success: '{result}'")
                return {"text": result, "provider": "deepgram"}
        except Exception as e:
            err_msg = f"Deepgram Error: {e}"
            print(f"[STT] {err_msg}")
            errors.append(err_msg)
            
    # 3. AssemblyAI (Tertiary)
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        try:
            print("[STT] Attempting AssemblyAI...")
            result = await transcribe_assemblyai(audio_content)
            if result:
                print(f"[STT] AssemblyAI Success: '{result}'")
                return {"text": result, "provider": "assemblyai"}
        except Exception as e:
            err_msg = f"AssemblyAI Error: {e}"
            print(f"[STT] {err_msg}")
            errors.append(err_msg)
            
    # If all failed or no keys are configured:
    raise HTTPException(
        status_code=500,
        detail=f"Speech recognition could not be performed. Errors: {errors}"
    )


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

