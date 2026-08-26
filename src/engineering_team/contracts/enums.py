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
    INCOMPLETE = "INCOMPLETE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class ErrorCode(StrEnum):
    PROJECT_CAPABILITY_ERROR = "PROJECT_CAPABILITY_ERROR"
    LLM_AVAILABILITY_ERROR = "LLM_AVAILABILITY_ERROR"
    LLM_QUALITY_ERROR = "LLM_QUALITY_ERROR"
    SECURITY_CONFLICT = "SECURITY_CONFLICT"
    TOOL_ERROR = "TOOL_ERROR"
    RAG_ERROR = "RAG_ERROR"
    CLOUD_FALLBACK_UNAVAILABLE = "CLOUD_FALLBACK_UNAVAILABLE"
    MCP_ERROR = "MCP_ERROR"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    NON_ACTIONABLE_REMEDIATION = "NON_ACTIONABLE_REMEDIATION"
    DEVELOPER_REMEDIATION_EXHAUSTED = "DEVELOPER_REMEDIATION_EXHAUSTED"


class ModelPriority(StrEnum):
    """Central runtime strategy governing per-role provider order."""

    CLOUD_FIRST = "cloud_first"
    LOCAL_FIRST = "local_first"
    CLOUD_ONLY = "cloud_only"
    LOCAL_ONLY = "local_only"


class DeveloperBlocker(StrEnum):
    """Structured reasons Developer may return instead of a mutation."""

    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    ARCHITECTURE_GAP = "ARCHITECTURE_GAP"
    REQUIREMENT_AMBIGUITY = "REQUIREMENT_AMBIGUITY"
    UNSAFE_CHANGE = "UNSAFE_CHANGE"


class ProjectCapabilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"


class ProjectEcosystem(StrEnum):
    PYTHON = "python"
    NODE = "node"
    DOTNET = "dotnet"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    UNKNOWN = "unknown"
