"""Bridge agent that sanitizes findings before checker visibility."""

import os

from state.case_state import CaseState
from shared.platform import case_trail_dir, contains_pii, repo_root_from, sanitize_copy, write_json


def sanitize_pii(case_state: CaseState) -> CaseState:
    """Sanitize findings before they cross the Bridge boundary.

    The Bridge exists so the checker never receives raw PII, even indirectly.
    """
    findings = case_state.findings

    pii_tokens = ["ahmed", "khan", "yasmeen", "akhtar", "muhammad", "ilyas", "karachi", "lahore", "rawalpindi"]
    if contains_pii(findings, pii_tokens):
        raise ValueError("PII Sanitizer Breach: Findings contain sensitive PII values.")

    case_state.sanitized_findings = sanitize_copy(findings)

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    os.makedirs(trail_dir, exist_ok=True)

    write_json(os.path.join(trail_dir, "12_sanitized_findings.json"), case_state.sanitized_findings)

    return case_state
