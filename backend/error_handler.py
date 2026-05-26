from enum import Enum
from typing import Dict, Any, Optional

class ErrorCategory(str, Enum):
    NETWORK = "NETWORK"
    SPEECH = "SPEECH"
    AI = "AI"
    QUEUE = "QUEUE"
    MEMORY = "MEMORY"

class ErrorSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class RecoveryAction(str, Enum):
    FALLBACK_REST = "FALLBACK_REST"
    MANUAL_INPUT = "MANUAL_INPUT"
    TEMPLATE_FALLBACK = "TEMPLATE_FALLBACK"
    COOLDOWN_RESET = "COOLDOWN_RESET"
    IGNORE = "IGNORE"

class SimulatorException(Exception):
    """Base exception for classroom simulator errors containing metadata."""
    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        severity: ErrorSeverity,
        recovery_action: RecoveryAction
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.recovery_action = recovery_action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": True,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "recovery_action": self.recovery_action.value
        }
