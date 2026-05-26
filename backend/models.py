from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class ClassroomSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    class_level = Column(String, nullable=False)
    lesson_objectives = Column(Text, nullable=True)
    teaching_method = Column(String, nullable=True)
    duration_minutes = Column(Integer, default=15)
    language = Column(String, default="English") # English, Hindi, Bengali
    scenario = Column(String, default="normal") # normal, low_attention, high_confusion, noisy, hyperactive, time_pressure
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship("SessionMessage", back_populates="session", cascade="all, delete-orphan")
    analytics = relationship("SessionAnalytics", back_populates="session", uselist=False, cascade="all, delete-orphan")
    student_states = relationship("StudentState", back_populates="session", cascade="all, delete-orphan")


class StudentState(Base):
    __tablename__ = "student_states"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    student_name = Column(String, nullable=False)
    attention_level = Column(Integer, default=80)     # 0 to 100
    confidence_level = Column(Integer, default=70)    # 0 to 100
    understanding_level = Column(Integer, default=75) # 0 to 100
    confusion_level = Column(Integer, default=20)     # 0 to 100
    curiosity_level = Column(Integer, default=50)     # 0 to 100 — driven by personality
    interrupt_probability = Column(Integer, default=20)  # 0 to 100
    memory_summary = Column(Text, nullable=True)      # Legacy: plain text summary
    memory_json = Column(Text, nullable=True)          # NEW: structured JSON memory
    participation_count = Column(Integer, default=0)

    session = relationship("ClassroomSession", back_populates="student_states")


class SessionMessage(Base):
    __tablename__ = "session_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    sender_type = Column(String, nullable=False)  # 'teacher', 'student', 'system'
    sender_name = Column(String, nullable=False)  # "Teacher", student name, or "System"
    message_text = Column(Text, nullable=False)
    student_personality = Column(String, nullable=True)  # 'Curious', 'Shy', etc.
    timestamp = Column(DateTime, default=datetime.utcnow)

    session = relationship("ClassroomSession", back_populates="messages")


class SessionAnalytics(Base):
    __tablename__ = "session_analytics"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), unique=True, nullable=False)
    communication_score = Column(Integer, default=0)
    engagement_score = Column(Integer, default=0)
    time_management_score = Column(Integer, default=0)
    question_handling_score = Column(Integer, default=0)
    suggestions = Column(Text, nullable=True)  # Detailed list / markdown advice
    transcript_summary = Column(Text, nullable=True)

    session = relationship("ClassroomSession", back_populates="analytics")
