from enum import StrEnum


class AgentRole(StrEnum):
    PRODUCT = "Product"
    ARCHITECTURE = "Architecture"
    DEVELOPER = "Developer"
    SECURITY = "Security"
    TESTING = "Testing"
    REVIEWER = "Reviewer"


class ReviewerStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SecuritySeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class ActionMode(StrEnum):
    PROPOSED = "PROPOSED"
    APPLIED = "APPLIED"


class ToolStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    DENIED = "DENIED"
    UNAVAILABLE = "UNAVAILABLE"


class RemediationCategory(StrEnum):
    ARCHITECTURE = "ARCHITECTURE"
    IMPLEMENTATION = "IMPLEMENTATION"
    SECURITY = "SECURITY"
    TESTING = "TESTING"


class RouteTarget(StrEnum):
    ARCHITECTURE = "Architecture"
    DEVELOPER = "Developer"
    TESTING = "Testing"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class ErrorCode(StrEnum):
    LLM_AVAILABILITY_ERROR = "LLM_AVAILABILITY_ERROR"
    LLM_QUALITY_ERROR = "LLM_QUALITY_ERROR"
    SECURITY_CONFLICT = "SECURITY_CONFLICT"
    TOOL_ERROR = "TOOL_ERROR"
    RAG_ERROR = "RAG_ERROR"
    CLOUD_FALLBACK_UNAVAILABLE = "CLOUD_FALLBACK_UNAVAILABLE"
    MCP_ERROR = "MCP_ERROR"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
