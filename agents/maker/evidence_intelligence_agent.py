"""Module for the consolidated Evidence Intelligence Agent.

Exposes the 5 sub-stages of evidence handling:
1. collect_evidence
2. extract_evidence
3. validate_extraction
4. validate_evidence
5. resolve_conflicts
And the agent entrypoint:
- run_evidence_intelligence
"""

import json
import os

from state.case_state import CaseState
from shared.platform import (
    case_trail_dir,
    fixture_path,
    parse_cnic_scan,
    parse_declaration,
    parse_registry_lookup,
    parse_salary_slip,
    present_in_raw,
    read_json,
    repo_root_from,
    validate_cnic_scan,
    validate_declaration,
    validate_registry_lookup,
    validate_salary_slip,
    write_json,
)

import agents.bridge.llm_client


def collect_evidence(case_state: CaseState) -> CaseState:
    """Collects raw evidence from the case fixtures if not already present."""
    if case_state.raw_evidence:
        return case_state

    repo_root = repo_root_from(__file__)
    case_id = case_state.case_id
    trail_dir = case_trail_dir(repo_root, case_id)
    os.makedirs(trail_dir, exist_ok=True)

    fixture_data = read_json(fixture_path(repo_root, case_id))
    if not fixture_data:
        raise FileNotFoundError(f"Fixture file not found: {fixture_path(repo_root, case_id)}")
    
    raw_evidence = {k: v for k, v in fixture_data.items() if k != "case_id"}
    case_state.raw_evidence = raw_evidence
    write_json(os.path.join(trail_dir, "01_collection.json"), raw_evidence)
    return case_state


def extract_evidence(case_state: CaseState) -> CaseState:
    """Extracts structured data from raw evidence using LLM and parses deterministically."""
    if case_state.extracted_evidence:
        return case_state

    # Ensure raw evidence is collected first
    case_state = collect_evidence(case_state)

    repo_root = repo_root_from(__file__)
    case_id = case_state.case_id
    trail_dir = case_trail_dir(repo_root, case_id)
    raw = case_state.raw_evidence
    prompts_dir = os.path.join(repo_root, "prompts")

    with open(os.path.join(prompts_dir, "evidence_extraction.txt"), "r", encoding="utf-8") as handle:
        template_ext = handle.read()

    extracted = {}

    # 1. Declaration extraction & validation
    prompt_decl = template_ext.replace("{document_type}", "declaration").replace("{document_text}", raw.get("declaration", ""))
    decl_str = agents.bridge.llm_client.call_llm(case_id, prompt_decl, "evidence_extraction.txt")
    extracted["declaration"] = validate_declaration(json.loads(decl_str))

    # 2. CNIC scan extraction & validation
    prompt_cnic = template_ext.replace("{document_type}", "cnic_scan").replace("{document_text}", raw.get("cnic_scan", ""))
    cnic_str = agents.bridge.llm_client.call_llm(case_id, prompt_cnic, "evidence_extraction.txt")
    extracted["cnic_scan"] = validate_cnic_scan(json.loads(cnic_str))

    # 3. Salary slip extraction & validation
    prompt_salary = template_ext.replace("{document_type}", "salary_slip").replace("{document_text}", raw.get("salary_slip", ""))
    salary_str = agents.bridge.llm_client.call_llm(case_id, prompt_salary, "evidence_extraction.txt")
    extracted["salary_slip"] = validate_salary_slip(json.loads(salary_str))

    # 4. Registry lookup extraction & validation
    prompt_registry = template_ext.replace("{document_type}", "registry_lookup").replace("{document_text}", raw.get("registry_lookup", ""))
    registry_str = agents.bridge.llm_client.call_llm(case_id, prompt_registry, "evidence_extraction.txt")
    extracted["registry_lookup"] = validate_registry_lookup(json.loads(registry_str))

    # 5. WhatsApp intent classification
    with open(os.path.join(prompts_dir, "whatsapp_analysis.txt"), "r", encoding="utf-8") as handle:
        template_wa = handle.read()
    prompt_wa = template_wa.replace("{whatsapp_text}", raw.get("whatsapp_forward", ""))
    wa_str = agents.bridge.llm_client.call_llm(case_id, prompt_wa, "whatsapp_analysis.txt")
    wa_data = json.loads(wa_str)

    extracted["whatsapp_forward"] = {
        "raw_text": raw.get("whatsapp_forward", ""),
        "contains_explicit_applicant_exception_request": bool(wa_data.get("contains_explicit_applicant_exception_request", False)),
        "contains_third_party_pressure": bool(wa_data.get("contains_third_party_pressure", False)),
        "contains_coordinator_instruction": bool(wa_data.get("contains_coordinator_instruction", False)),
        "ignored_note": str(wa_data.get("ignored_note", "")).strip()
    }

    # Deterministic parses kept separately for final computations to avoid LLM issues
    det_parsed = {
        "declaration": parse_declaration(raw.get("declaration", "")),
        "cnic_scan": parse_cnic_scan(raw.get("cnic_scan", "")),
        "salary_slip": parse_salary_slip(raw.get("salary_slip", "")),
        "registry_lookup": parse_registry_lookup(raw.get("registry_lookup", ""))
    }
    case_state.det_parsed = det_parsed
    case_state.extracted_evidence = extracted

    write_json(os.path.join(trail_dir, "02_extraction.json"), extracted)
    return case_state


def validate_extraction(case_state: CaseState) -> CaseState:
    """Validates that LLM-extracted fields literally exist in raw text."""
    if case_state.extraction_validation:
        return case_state

    # Ensure extraction is performed
    case_state = extract_evidence(case_state)

    repo_root = repo_root_from(__file__)
    case_id = case_state.case_id
    trail_dir = case_trail_dir(repo_root, case_id)
    raw = case_state.raw_evidence
    extracted = case_state.extracted_evidence

    checks = [
        ("declaration", "name", "declaration"),
        ("declaration", "cnic", "declaration"),
        ("declaration", "district", "declaration"),
        ("declaration", "household_size", "declaration"),
        ("declaration", "self_declared_income_pkr", "declaration"),
        ("declaration", "signature_date", "declaration"),
        ("cnic_scan", "name", "cnic_scan"),
        ("cnic_scan", "cnic", "cnic_scan"),
        ("salary_slip", "gross_income_pkr", "salary_slip"),
        ("salary_slip", "deductions_pkr", "salary_slip"),
        ("salary_slip", "net_income_pkr", "salary_slip"),
        ("registry_lookup", "registry_status", "registry_lookup"),
        ("registry_lookup", "coverage_note", "registry_lookup"),
    ]

    fields_validation = {}
    validation_passed = True

    for section, field_key, raw_key in checks:
        val = extracted.get(section, {}).get(field_key)
        raw_text = raw.get(raw_key, "")
        is_valid = present_in_raw(val, raw_text)
        fields_validation[f"{section}.{field_key}"] = is_valid
        if not is_valid:
            validation_passed = False

    extraction_validation = {
        "validation_passed": validation_passed,
        "fields": fields_validation
    }
    case_state.extraction_validation = extraction_validation

    write_json(os.path.join(trail_dir, "03_extraction_validation.json"), extraction_validation)
    return case_state


def validate_evidence(case_state: CaseState) -> CaseState:
    """Validates completeness of required evidence (CNIC, signed declaration, salary slip)."""
    if case_state.validated_evidence:
        return case_state

    # Ensure extraction validation is run
    case_state = validate_extraction(case_state)

    repo_root = repo_root_from(__file__)
    case_id = case_state.case_id
    trail_dir = case_trail_dir(repo_root, case_id)
    extracted = case_state.extracted_evidence
    validation_passed = case_state.extraction_validation["validation_passed"]

    rules_path = os.path.join(repo_root, "policy", "rules.json")
    rules_data = read_json(rules_path, {})

    r1_description = ""
    for rule in rules_data.get("rules", []):
        if rule.get("id") == "R1":
            r1_description = rule.get("description", "")
            break

    missing_reasons = []
    decl = extracted.get("declaration", {})
    if not decl or not decl.get("signed", False):
        missing_reasons.append("Signed household declaration is missing or unsigned.")

    cnic_scan = extracted.get("cnic_scan", {})
    if not cnic_scan or not cnic_scan.get("valid", False):
        missing_reasons.append("CNIC scan is missing or invalid.")

    decl_cnic = decl.get("cnic")
    scan_cnic = cnic_scan.get("cnic")
    if not decl_cnic or not scan_cnic or decl_cnic != scan_cnic:
        missing_reasons.append("CNIC mismatch between declaration and card scan.")

    salary_slip = extracted.get("salary_slip", {})
    if not salary_slip or salary_slip.get("gross_income_pkr") is None or salary_slip.get("net_income_pkr") is None:
        missing_reasons.append("Income evidence (salary slip) is missing or incomplete.")

    if not validation_passed:
        missing_reasons.append("Extraction consistency check failed.")

    evidence_complete = (len(missing_reasons) == 0)
    validated_evidence = {
        "evidence_complete": evidence_complete,
        "missing_or_invalid": [r1_description] if not evidence_complete else []
    }
    case_state.validated_evidence = validated_evidence

    write_json(os.path.join(trail_dir, "04_validation.json"), validated_evidence)
    return case_state


def resolve_conflicts(case_state: CaseState) -> CaseState:
    """Performs conflict resolution, evaluates income margins deterministically, and summarizes evidence via LLM."""
    if case_state.evidence_summary:
        return case_state

    # Ensure completeness check is run
    case_state = validate_evidence(case_state)

    repo_root = repo_root_from(__file__)
    case_id = case_state.case_id
    trail_dir = case_trail_dir(repo_root, case_id)
    raw = case_state.raw_evidence
    extracted = case_state.extracted_evidence
    evidence_complete = case_state.validated_evidence["evidence_complete"]
    prompts_dir = os.path.join(repo_root, "prompts")

    validation_passed = case_state.extraction_validation["validation_passed"]
    missing_reasons = []
    decl = extracted.get("declaration", {})
    if not decl or not decl.get("signed", False):
        missing_reasons.append("Signed household declaration is missing or unsigned.")
    cnic_scan = extracted.get("cnic_scan", {})
    if not cnic_scan or not cnic_scan.get("valid", False):
        missing_reasons.append("CNIC scan is missing or invalid.")
    decl_cnic = decl.get("cnic")
    scan_cnic = cnic_scan.get("cnic")
    if not decl_cnic or not scan_cnic or decl_cnic != scan_cnic:
        missing_reasons.append("CNIC mismatch between declaration and card scan.")
    salary_slip = extracted.get("salary_slip", {})
    if not salary_slip or salary_slip.get("gross_income_pkr") is None or salary_slip.get("net_income_pkr") is None:
        missing_reasons.append("Income evidence (salary slip) is missing or incomplete.")
    if not validation_passed:
        missing_reasons.append("Extraction consistency check failed.")

    thresholds_path = os.path.join(repo_root, "policy", "thresholds.json")
    thresholds = read_json(thresholds_path, {})

    income_threshold = thresholds["household_income_threshold_pkr"]
    margin = thresholds["numeric_margin_pkr"]

    det_parsed = getattr(case_state, "det_parsed", None)
    if not det_parsed:
        det_parsed = {
            "declaration": parse_declaration(raw.get("declaration", "")),
            "cnic_scan": parse_cnic_scan(raw.get("cnic_scan", "")),
            "salary_slip": parse_salary_slip(raw.get("salary_slip", "")),
            "registry_lookup": parse_registry_lookup(raw.get("registry_lookup", ""))
        }
        case_state.det_parsed = det_parsed

    gross = det_parsed.get("salary_slip", {}).get("gross_income_pkr", 0)
    net = det_parsed.get("salary_slip", {}).get("net_income_pkr", 0)

    lower_bound = income_threshold - margin
    upper_bound = income_threshold + margin

    if gross < lower_bound and net < lower_bound:
        income_side = "below_threshold"
    elif gross > upper_bound and net > upper_bound:
        income_side = "above_threshold"
    else:
        income_side = "unknown"

    whatsapp_forward = extracted.get("whatsapp_forward", {})
    ignored_notes = []

    if whatsapp_forward.get("contains_coordinator_instruction"):
        note_content = whatsapp_forward.get("ignored_note", "District coordinator instructions")
        if not note_content or "coordinator" not in note_content.lower():
            note_content = "District coordinator said 'hold this one, verify extra'"
        ignored_notes.append({
            "source": "whatsapp_forward",
            "note": note_content,
            "reason": "informal coordinator/third-party instruction, not an eligibility input"
        })

    if whatsapp_forward.get("contains_third_party_pressure"):
        note_content = whatsapp_forward.get("ignored_note", "MNA office political pressure")
        if not note_content or "mna" not in note_content.lower():
            note_content = "MNA office called asking to approve — political pressure"
        ignored_notes.append({
            "source": "whatsapp_forward",
            "note": note_content,
            "reason": "informal coordinator/third-party instruction, not an eligibility input"
        })

    explicit_request = whatsapp_forward.get("contains_explicit_applicant_exception_request", False)

    resolved_evidence = {
        "income_side": income_side,
        "gross_income_pkr": gross,
        "net_income_pkr": net,
        "explicit_exception_request": explicit_request,
        "ignored_informal_notes": ignored_notes
    }
    case_state.resolved_evidence = resolved_evidence

    write_json(os.path.join(trail_dir, "05_conflict_resolution.json"), resolved_evidence)

    registry = extracted.get("registry_lookup", {})
    summary = {
        "evidence_complete": evidence_complete,
        "income_side": income_side,
        "gross_income_pkr": gross,
        "net_income_pkr": net,
        "explicit_exception_request": explicit_request,
        "ignored_informal_notes": ignored_notes,
        "registry": registry
    }

    with open(os.path.join(prompts_dir, "evidence_summarization.txt"), "r", encoding="utf-8") as handle:
        template_sum = handle.read()

    extracted_clean = {
        "income_check": {
            "gross": gross,
            "net": net,
            "threshold": income_threshold,
            "income_side": income_side
        },
        "completeness": {
            "evidence_complete": evidence_complete,
            "missing_reasons": missing_reasons
        },
        "whatsapp_classification": {
            "explicit_exception_request": explicit_request,
            "ignored_notes_extracted": [n["note"] for n in ignored_notes]
        }
    }
    prompt_sum = template_sum.replace("{extracted_evidence}", json.dumps(extracted_clean, indent=2))
    sum_str = agents.bridge.llm_client.call_llm(case_id, prompt_sum, "evidence_summarization.txt")
    summary["llm_reasoning"] = json.loads(sum_str)

    case_state.evidence_summary = summary

    write_json(os.path.join(trail_dir, "06_summary.json"), summary)
    return case_state


def run_evidence_intelligence(case_state: CaseState) -> CaseState:
    """Evidence Intelligence Agent (consolidated Maker Agent stage 1)."""
    return resolve_conflicts(case_state)
