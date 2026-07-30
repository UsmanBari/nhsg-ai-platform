"""Schema models representing benefit-disbursement system records.

These models define data containers that represent findings, public roll,
and decision records. No runtime validation is executed yet.
"""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class FlagsStub:
    """Flags detailing evaluation state for findings."""

    income_side: str
    evidence_complete: bool
    duplicate_flag: bool
    explicit_exception_request: bool


@dataclass
class FindingsStub:
    """Structured verifier findings that pass through the sanitization bridge."""

    case_ref: str
    verifier_decision: str
    rules_fired: List[str]
    flags: FlagsStub
    decision_record_ref: str


@dataclass
class PublicRollStub:
    """Details for a public disbursement roll entry."""

    case_ref: str
    amount_pkr: float


@dataclass
class EvidenceIgnoredStub:
    """Details of evidence items that were ignored and why."""

    item: str
    reason: str


@dataclass
class PolicyAppliedStub:
    """Versions of rules and thresholds policy applied."""

    policy_version: str
    thresholds_version: str


@dataclass
class EngineeringConfidenceStub:
    """Quality engineering checklists for validation confidence."""

    evidence_complete: str
    rule_order_verified: str
    decision_independently_validated: str


@dataclass
class DecisionRecordStub:
    """Detailed record explaining eligibility decision rationale and policy applied."""

    case_ref: str
    decision: str
    rule_fired: str
    evidence_used: List[str]
    evidence_ignored: List[EvidenceIgnoredStub]
    policy_applied: PolicyAppliedStub
    explanation: str
    engineering_confidence: EngineeringConfidenceStub
    timestamp: str
