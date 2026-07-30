"""Utility for mocking the LLM agent responses during deterministic tests."""

import json


def mock_call_llm_impl(case_id: str, prompt: str, prompt_version: str, response_json_mode: bool = True) -> str:
    """Mock implementation of the call_llm function for unit testing."""
    if prompt_version == "evidence_extraction.txt":
        # Legacy/Test document extraction mocks
        if "Document Type: declaration" in prompt:
            if "CASE-001" in case_id:
                return json.dumps({
                    "name": "Ahmed Khan",
                    "cnic": "42101-2222222-3",
                    "district": "Karachi East, UC-33",
                    "household_size": 3,
                    "other_earners_declared": False,
                    "self_declared_income_pkr": 42000,
                    "signed": True,
                    "signature_date": "16/06/2026"
                })
            elif "CASE-002" in case_id:
                return json.dumps({
                    "name": "Yasmeen Akhtar",
                    "cnic": "35202-3333333-4",
                    "district": "Lahore, UC-08",
                    "household_size": 5,
                    "other_earners_declared": False,
                    "self_declared_income_pkr": 38000,
                    "signed": True,
                    "signature_date": "17/06/2026"
                })
            elif "CASE-003" in case_id:
                return json.dumps({
                    "name": "Muhammad Ilyas",
                    "cnic": "37405-0101010-1",
                    "district": "Rawalpindi, UC-07",
                    "household_size": 6,
                    "other_earners_declared": False,
                    "self_declared_income_pkr": 48000,
                    "signed": True,
                    "signature_date": "23/06/2026"
                })
        elif "Document Type: cnic_scan" in prompt:
            if "CASE-001" in case_id:
                return json.dumps({"name": "Ahmed Khan", "cnic": "42101-2222222-3", "valid": True})
            elif "CASE-002" in case_id:
                return json.dumps({"name": "Yasmeen Akhtar", "cnic": "35202-3333333-4", "valid": True})
            elif "CASE-003" in case_id:
                return json.dumps({"name": "Muhammad Ilyas", "cnic": "37405-0101010-1", "valid": True})
        elif "Document Type: salary_slip" in prompt:
            if "CASE-001" in case_id:
                return json.dumps({"employer": "KARACHI PORT TRUST", "gross_income_pkr": 44000, "deductions_pkr": 3200, "net_income_pkr": 40800})
            elif "CASE-002" in case_id:
                return json.dumps({"employer": "UNIVERSITY OF THE PUNJAB", "gross_income_pkr": 62000, "deductions_pkr": 5500, "net_income_pkr": 56500})
            elif "CASE-003" in case_id:
                return json.dumps({"employer": "ATTOCK CEMENT PAKISTAN LTD", "gross_income_pkr": 52000, "deductions_pkr": 3500, "net_income_pkr": 48500})
        elif "Document Type: registry_lookup" in prompt:
            if "CASE-001" in case_id:
                return json.dumps({"identity_verified": True, "registry_status": "ACTIVE_CITIZEN", "flags": [], "active_grants_other_districts": [], "coverage_note": "ALL_DISTRICTS_CHECKED"})
            elif "CASE-002" in case_id:
                return json.dumps({"identity_verified": True, "registry_status": "ACTIVE_CITIZEN", "flags": [], "active_grants_other_districts": [], "coverage_note": "ALL_DISTRICTS_CHECKED"})
            elif "CASE-003" in case_id:
                return json.dumps({"identity_verified": True, "registry_status": "ACTIVE_CITIZEN", "flags": [], "active_grants_other_districts": [], "coverage_note": "ALL_DISTRICTS_CHECKED"})

    elif prompt_version == "evidence_summarization.txt":
        if "CASE-001" in case_id:
            return json.dumps({
                "evidence_summary": "Ahmed Khan UC-33 application contains signed declaration, valid CNIC, and Karachi Port Trust pay slip showing income below the threshold.",
                "contradictions_explanation": "None. Self-declared income of 42k matches verified crane operator salary parameters.",
                "ignored_notes_explanation": "Disregarded district coordinator note to hold the case because informal instruction is not an eligibility input."
            })
        elif "CASE-002" in case_id:
            return json.dumps({
                "evidence_summary": "Yasmeen Akhtar UC-08 application contains signed declaration, valid CNIC, and pay slip showing income above the threshold.",
                "contradictions_explanation": "Self-declared monthly income of 38k is overridden by the verified university gross salary of 62k and net pay of 56.5k, both exceeding 50k.",
                "ignored_notes_explanation": "Disregarded MNA office request to approve since political pressure is not an eligibility input."
            })
        elif "CASE-003" in case_id:
            return json.dumps({
                "evidence_summary": "Muhammad Ilyas UC-07 application contains signed declaration, valid CNIC, and Attock Cement pay slip showing income close to the threshold.",
                "contradictions_explanation": "Verified gross salary of 52k is inside the margin boundary, leading to an unknown income side determination.",
                "ignored_notes_explanation": "None. The applicant's request to override is not a third-party pressure but an explicit authorization request."
            })

    elif prompt_version == "whatsapp_analysis.txt":
        if "CASE-001" in case_id:
            return json.dumps({
                "contains_explicit_applicant_exception_request": False,
                "contains_third_party_pressure": False,
                "contains_coordinator_instruction": True,
                "ignored_note": "District coordinator said 'hold this one, verify extra' but no rule cited."
            })
        elif "CASE-002" in case_id:
            return json.dumps({
                "contains_explicit_applicant_exception_request": False,
                "contains_third_party_pressure": True,
                "contains_coordinator_instruction": False,
                "ignored_note": "MNA office called asking to approve — political pressure"
            })
        elif "CASE-003" in case_id:
            return json.dumps({
                "contains_explicit_applicant_exception_request": True,
                "contains_third_party_pressure": False,
                "contains_coordinator_instruction": False,
                "ignored_note": ""
            })

    elif prompt_version == "decision_explainer.txt":
        if "CASE-001" in case_id:
            return "All preliminary eligibility rules R1-R5 passed successfully. Verification of the remaining grant pool balance is pending."
        elif "CASE-002" in case_id:
            return "Verified household income exceeds the eligibility threshold."
        elif "CASE-003" in case_id:
            return "An explicit exception request was submitted by the applicant for review."

    if response_json_mode:
        return "{}"
    return "Default mock explanation."
