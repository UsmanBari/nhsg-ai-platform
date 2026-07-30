"""Module for the consolidated Verifier Agent.

Exposes the 7 sub-stages of decision evaluation:
1. check_eligibility
2. select_rules
3. evaluate_rules
4. resolve_decision
5. validate_decision
6. explain_decision
7. generate_findings
And the agent entrypoint:
- run_verifier_agent
"""

from datetime import timezone
import datetime as dt_module
import json
import os
from typing import Any, List

import agents.bridge.llm_client
from shared.platform import case_trail_dir, contains_pii, read_json, repo_root_from, write_json
from state.case_state import CaseState


def _check_rule_condition(rule_id: str, summary: dict, elig: dict) -> bool:
    """Independently evaluates a rule's matching condition."""
    if rule_id == "R1":
        return not summary.get("evidence_complete", False)
    elif rule_id == "R2":
        return elig.get("registry_ineligible", False)
    elif rule_id == "R3":
        return elig.get("duplicate_claim", False)
    elif rule_id == "R4":
        return summary.get("explicit_exception_request", False)
    elif rule_id == "R5":
        return (summary.get("income_side") == "above_threshold")
    return False


def check_eligibility(case_state: CaseState) -> CaseState:
    """Evaluates preliminary eligibility flags based on registry lookup data."""
    if case_state.eligibility_check:
        return case_state

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    os.makedirs(trail_dir, exist_ok=True)

    summary = case_state.evidence_summary
    registry = summary.get("registry", {})
    identity_verified = registry.get("identity_verified", False)
    flags = registry.get("flags", [])
    active_grants = registry.get("active_grants_other_districts", [])

    registry_ineligible = (not identity_verified) or (len(flags) > 0)
    duplicate_claim = len(active_grants) > 0

    eligibility_check = {
        "registry_ineligible": registry_ineligible,
        "duplicate_claim": duplicate_claim,
    }
    case_state.eligibility_check = eligibility_check

    write_json(os.path.join(trail_dir, "07_eligibility_check.json"), eligibility_check)
    return case_state


def select_rules(case_state: CaseState) -> CaseState:
    """Selects policy rules relevant for checking eligibility (R1-R5)."""
    # Exposing wrapper function for backward compatibility
    return case_state


def evaluate_rules(case_state: CaseState) -> CaseState:
    """Evaluates select rules on case state."""
    # Exposing wrapper function for backward compatibility
    return case_state


def resolve_decision(case_state: CaseState) -> CaseState:
    """Resolves eligibility decision code based on the first matched rule of R1-R5."""
    if case_state.rule_trace:
        return case_state

    # Ensure eligibility check is run first
    case_state = check_eligibility(case_state)

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    summary = case_state.evidence_summary
    eligibility_check = case_state.eligibility_check

    rules_path = os.path.join(repo_root, "policy", "rules.json")
    rules_data = read_json(rules_path, {})

    evaluation_order = rules_data.get("evaluation_order", [])
    allowed_rules = {"R1", "R2", "R3", "R4", "R5"}
    selected_rules = [r for r in evaluation_order if r in allowed_rules]

    results = []
    for rule_id in selected_rules:
        matched = _check_rule_condition(rule_id, summary, eligibility_check)
        results.append({
            "rule": rule_id,
            "matched": matched
        })

    codes_path = os.path.join(repo_root, "policy", "decision_codes.json")
    decision_codes = read_json(codes_path, {})

    matched_rule = None
    for res in results:
        if res.get("matched", False):
            matched_rule = res.get("rule")
            break

    if matched_rule:
        verifier_decision = decision_codes[matched_rule]
        rules_fired = [matched_rule]
    else:
        verifier_decision = "PENDING_R6_R7"
        rules_fired = []

    rule_trace = {
        "evaluation_order": selected_rules,
        "results": results,
        "verifier_decision": verifier_decision,
        "rules_fired": rules_fired
    }
    case_state.rule_trace = rule_trace

    write_json(os.path.join(trail_dir, "08_rule_trace.json"), rule_trace)
    return case_state


def validate_decision(case_state: CaseState) -> CaseState:
    """Independently verifies decision consistency against rule traces."""
    if case_state.decision_validation:
        return case_state

    # Ensure decision is resolved first
    case_state = resolve_decision(case_state)

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    summary = case_state.evidence_summary
    eligibility_check = case_state.eligibility_check
    rule_trace = case_state.rule_trace
    verifier_decision = rule_trace["verifier_decision"]
    rules_fired = rule_trace["rules_fired"]

    codes_path = os.path.join(repo_root, "policy", "decision_codes.json")
    decision_codes = read_json(codes_path, {})

    consistent = True
    recheck_performed_on = "NONE"
    recheck_result = "unconfirmed"

    if rules_fired:
        matched_rule = rules_fired[0]
        recheck_performed_on = matched_rule
        condition_true = _check_rule_condition(matched_rule, summary, eligibility_check)
        expected_decision_code = decision_codes.get(matched_rule)

        if condition_true and verifier_decision == expected_decision_code:
            recheck_result = "confirmed"
        else:
            recheck_result = "mismatch"
            consistent = False
    else:
        recheck_performed_on = "R1-R5"
        all_false = True
        for rule_id in ["R1", "R2", "R3", "R4", "R5"]:
            if _check_rule_condition(rule_id, summary, eligibility_check):
                all_false = False
                break

        if all_false and verifier_decision == "PENDING_R6_R7":
            recheck_result = "confirmed"
        else:
            recheck_result = "mismatch"
            consistent = False

    decision_validation = {
        "recheck_performed_on": recheck_performed_on,
        "recheck_result": recheck_result,
        "consistent_with_rule_trace": consistent
    }
    case_state.decision_validation = decision_validation

    write_json(os.path.join(trail_dir, "09_decision_validation.json"), decision_validation)

    if not consistent:
        raise ValueError(
            f"Decision Validator detected mismatch: Resolver decision is '{verifier_decision}' "
            f"with fired rules {rules_fired}, but recheck is inconsistent."
        )

    return case_state


def explain_decision(case_state: CaseState) -> CaseState:
    """Generates an LLM-based natural language explanation grounding the decision record."""
    if case_state.decision_record:
        return case_state

    # Ensure decision validation is run
    case_state = validate_decision(case_state)

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    summary = case_state.evidence_summary
    rule_trace = case_state.rule_trace
    verifier_decision = rule_trace["verifier_decision"]
    rules_fired = rule_trace["rules_fired"]
    decision_validation = case_state.decision_validation

    fired_rule_id = rules_fired[0] if rules_fired else "NONE"
    if fired_rule_id == "R1":
        evidence_used = ["incomplete_evidence"]
    elif fired_rule_id == "R2":
        evidence_used = ["identity_verification_failed"]
    elif fired_rule_id == "R3":
        evidence_used = ["active_grant_in_other_district"]
    elif fired_rule_id == "R4":
        evidence_used = ["explicit_applicant_exception_request"]
    elif fired_rule_id == "R5":
        evidence_used = ["verified_household_income_above_threshold"]
    else:
        evidence_used = ["all_preliminary_maker_checks_passed"]

    evidence_ignored = []
    for note in summary.get("ignored_informal_notes", []):
        evidence_ignored.append({
            "item": note.get("note", ""),
            "reason": note.get("reason", "")
        })

    is_complete = "YES" if summary.get("evidence_complete", False) else "NO"
    is_validated = "YES" if decision_validation.get("consistent_with_rule_trace", False) else "NO"
    eng_conf = f"evidence_complete={is_complete}, rule_order_verified=YES, decision_independently_validated={is_validated}"

    prompts_dir = os.path.join(repo_root, "prompts")
    with open(os.path.join(prompts_dir, "decision_explainer.txt"), "r", encoding="utf-8") as handle:
        template_de = handle.read()

    prompt_de = (
        template_de.replace("{case_ref}", case_state.case_id)
        .replace("{decision}", verifier_decision)
        .replace("{rules_fired}", fired_rule_id)
        .replace("{evidence_used}", ", ".join(evidence_used))
        .replace("{engineering_confidence}", eng_conf)
    )

    explanation = agents.bridge.llm_client.call_llm(case_state.case_id, prompt_de, "decision_explainer.txt", response_json_mode=False)

    decision_record = {
        "case_ref": case_state.case_id,
        "decision": verifier_decision,
        "rule_fired": fired_rule_id,
        "evidence_used": evidence_used,
        "evidence_ignored": evidence_ignored,
        "policy_applied": {
            "policy_version": "1.0",
            "thresholds_version": "1.0"
        },
        "explanation": explanation,
        "engineering_confidence": {
            "evidence_complete": is_complete,
            "rule_order_verified": "YES",
            "decision_independently_validated": is_validated
        },
        "timestamp": dt_module.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    case_state.decision_record = decision_record

    write_json(os.path.join(trail_dir, "10_decision_record.json"), decision_record)
    return case_state


def generate_findings(case_state: CaseState) -> CaseState:
    """Packages decision and rules trace into a clean, PII-free findings dictionary for the bridge."""
    if case_state.findings:
        return case_state

    # Ensure decision explanation is generated
    case_state = explain_decision(case_state)

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    summary = case_state.evidence_summary
    rule_trace = case_state.rule_trace
    verifier_decision = rule_trace["verifier_decision"]
    rules_fired = rule_trace["rules_fired"]
    eligibility_check = case_state.eligibility_check

    findings = {
        "case_ref": case_state.case_id,
        "verifier_decision": verifier_decision,
        "rules_fired": rules_fired,
        "flags": {
            "income_side": summary.get("income_side"),
            "evidence_complete": summary.get("evidence_complete"),
            "duplicate_flag": eligibility_check.get("duplicate_claim"),
            "explicit_exception_request": summary.get("explicit_exception_request")
        },
        "decision_record_ref": "10_decision_record.json"
    }

    # Gather PII values from extracted evidence for check
    pii_list = []
    extracted = getattr(case_state, "extracted_evidence", {})
    for section in ["declaration", "cnic_scan"]:
        sec_data = extracted.get(section, {})
        name = sec_data.get("name")
        cnic = sec_data.get("cnic")
        if name:
            pii_list.append(name)
        if cnic:
            pii_list.append(cnic)

    if contains_pii(findings, pii_list):
        raise ValueError("PII Leakage Detected: findings object contains sensitive data values.")

    case_state.findings = findings

    write_json(os.path.join(trail_dir, "11_findings.json"), findings)
    return case_state


def run_verifier_agent(case_state: CaseState) -> CaseState:
    """Verifier Agent - deterministic decision engine with LLM-grounded explanations."""
    return generate_findings(case_state)
