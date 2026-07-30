"""State model representation for benefit disbursement cases.

Defines the CaseState dataclass that aggregates and tracks state modifications
by individual agents across the pipelines.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CaseState:
    """Represents the complete state of a single benefit-disbursement case.

    Each section of this state is owned by a single agent which is allowed to
    write to it. Agents can read previous sections.
    """

    case_id: str
    raw_evidence: Dict[str, Any] = field(default_factory=dict)
    extracted_evidence: Dict[str, Any] = field(default_factory=dict)
    extraction_validation: Dict[str, Any] = field(default_factory=dict)
    validated_evidence: Dict[str, Any] = field(default_factory=dict)
    resolved_evidence: Dict[str, Any] = field(default_factory=dict)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    eligibility_check: Dict[str, Any] = field(default_factory=dict)
    rule_trace: Dict[str, Any] = field(default_factory=dict)
    decision_validation: Dict[str, Any] = field(default_factory=dict)
    decision_record: Dict[str, Any] = field(default_factory=dict)
    findings: Dict[str, Any] = field(default_factory=dict)
    sanitized_findings: Dict[str, Any] = field(default_factory=dict)
    pool_decision: Dict[str, Any] = field(default_factory=dict)
    transaction: Dict[str, Any] = field(default_factory=dict)
    public_roll_entry: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the CaseState instance to a standard Python dictionary."""
        return {
            "case_id": self.case_id,
            "raw_evidence": self.raw_evidence,
            "extracted_evidence": self.extracted_evidence,
            "extraction_validation": self.extraction_validation,
            "validated_evidence": self.validated_evidence,
            "resolved_evidence": self.resolved_evidence,
            "evidence_summary": self.evidence_summary,
            "eligibility_check": self.eligibility_check,
            "rule_trace": self.rule_trace,
            "decision_validation": self.decision_validation,
            "decision_record": self.decision_record,
            "findings": self.findings,
            "sanitized_findings": self.sanitized_findings,
            "pool_decision": self.pool_decision,
            "transaction": self.transaction,
            "public_roll_entry": self.public_roll_entry,
        }
