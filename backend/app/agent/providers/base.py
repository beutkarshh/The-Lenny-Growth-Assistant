from dataclasses import dataclass, field


@dataclass
class AgentResult:
    content: str
    citations: list[dict] = field(default_factory=list)
    # Set only when ship30_essay produced a document this turn (Phase 5).
    artifact_content: str | None = None
    artifact_type: str | None = None
