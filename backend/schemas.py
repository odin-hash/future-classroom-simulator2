from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class SessionMessageBase(BaseModel):
    sender_type: str  # 'teacher', 'student', 'system'
    sender_name: str
    message_text: str
    student_personality: Optional[str] = None


class SessionMessageCreate(SessionMessageBase):
    pass


class SessionMessageOut(SessionMessageBase):
    id: int
    session_id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class ClassroomSessionBase(BaseModel):
    subject: str
    topic: str
    class_level: str
    lesson_objectives: Optional[str] = None
    teaching_method: Optional[str] = None
    duration_minutes: int = 15
    language: str = "English"  # English, Hindi, Bengali
    scenario: str = "normal"  # normal, low_attention, high_confusion, noisy, hyperactive, time_pressure


class StudentStateBase(BaseModel):
    student_name: str
    attention_level: int
    confidence_level: int
    understanding_level: int
    confusion_level: int
    memory_summary: Optional[str] = None
    participation_count: int = 0


class StudentStateCreate(StudentStateBase):
    pass


class StudentStateOut(StudentStateBase):
    id: int
    session_id: int

    class Config:
        from_attributes = True


class ClassroomSessionCreate(ClassroomSessionBase):
    pass


class ClassroomSessionOut(ClassroomSessionBase):
    id: int
    created_at: datetime
    messages: List[SessionMessageOut] = []
    student_states: List[StudentStateOut] = []

    class Config:
        from_attributes = True


class SessionAnalyticsBase(BaseModel):
    communication_score: int
    engagement_score: int
    time_management_score: int
    question_handling_score: int
    suggestions: str
    transcript_summary: Optional[str] = None


class SessionAnalyticsCreate(SessionAnalyticsBase):
    session_id: int


class SessionAnalyticsOut(SessionAnalyticsBase):
    id: int
    session_id: int

    class Config:
        from_attributes = True


class TeacherTurnInput(BaseModel):
    message: str
    addressed_student: Optional[str] = None  # Name of student specifically addressed, if any
    action: Optional[str] = None  # Action to perform, e.g., "focus", "explain_basic", etc.
    active_event_id: Optional[str] = None
    responder_queue: Optional[str] = None
    elapsed_ratio: Optional[float] = None
    is_demo: Optional[bool] = False


