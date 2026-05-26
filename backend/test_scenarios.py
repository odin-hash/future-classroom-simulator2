import os
import sys
import json
import unittest

# Dynamically add backend to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base, engine, SessionLocal
from models import StudentState, ClassroomSession
from main import create_session
from schemas import ClassroomSessionCreate

class TestClassroomScenarios(unittest.TestCase):
    def setUp(self):
        # Initialize test database
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_low_attention_scenario(self):
        session_data = ClassroomSessionCreate(
            subject="Science",
            topic="Gravity",
            class_level="Primary (Grades 1-5)",
            duration_minutes=10,
            language="English",
            scenario="low_attention"
        )
        session = create_session(session_data, self.db)
        
        # Verify that all student states start with attention = 25
        states = self.db.query(StudentState).filter(StudentState.session_id == session.id).all()
        self.assertEqual(len(states), 6)
        for s in states:
            self.assertEqual(s.attention_level, 25, f"{s.student_name} attention should override to 25")

    def test_high_confusion_scenario(self):
        session_data = ClassroomSessionCreate(
            subject="Maths",
            topic="Algebra",
            class_level="High School (Grades 9-12)",
            duration_minutes=15,
            language="English",
            scenario="high_confusion"
        )
        session = create_session(session_data, self.db)
        
        # Verify that all student states start with confusion = 80 and understanding = 25
        states = self.db.query(StudentState).filter(StudentState.session_id == session.id).all()
        self.assertEqual(len(states), 6)
        for s in states:
            self.assertEqual(s.confusion_level, 80, f"{s.student_name} confusion should override to 80")
            self.assertEqual(s.understanding_level, 25, f"{s.student_name} understanding should override to 25")

    def test_hyperactive_scenario(self):
        session_data = ClassroomSessionCreate(
            subject="History",
            topic="World War",
            class_level="Middle School (Grades 6-8)",
            duration_minutes=15,
            language="English",
            scenario="hyperactive"
        )
        session = create_session(session_data, self.db)
        
        states = self.db.query(StudentState).filter(StudentState.session_id == session.id).all()
        for s in states:
            if s.student_name in ["Ishaan", "Kabir"]:
                self.assertEqual(s.interrupt_probability, 90, f"{s.student_name} should have 90% interrupt")
                self.assertEqual(s.curiosity_level, 95, f"{s.student_name} should have 95% curiosity")

if __name__ == "__main__":
    unittest.main()
