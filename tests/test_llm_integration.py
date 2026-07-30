"""Unit tests for LLM integration, schema validation, retry logic, and error scenarios."""

import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state.case_state import CaseState
from agents.bridge.llm_client import call_llm
from agents.maker.evidence_intelligence_agent import (
    extract_evidence,
    validate_extraction,
    validate_evidence,
    resolve_conflicts,
)
from agents.maker.verifier_agent import explain_decision


class TestLLMIntegration(unittest.TestCase):
    """Verifies valid/malformed JSON, retries, schemas, and validator bounds."""

    def setUp(self) -> None:
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.case_id = "CASE-999"
        self.trail_dir = os.path.join(self.repo_root, "evidence_trail", self.case_id)
        
        # Ensure cleanup of CASE-999 directories if left over
        if os.path.exists(self.trail_dir):
            for f in os.listdir(self.trail_dir):
                try:
                    os.remove(os.path.join(self.trail_dir, f))
                except OSError:
                    pass
            try:
                os.rmdir(self.trail_dir)
            except OSError:
                pass

    def tearDown(self) -> None:
        if os.path.exists(self.trail_dir):
            for f in os.listdir(self.trail_dir):
                try:
                    os.remove(os.path.join(self.trail_dir, f))
                except OSError:
                    pass
            try:
                os.rmdir(self.trail_dir)
            except OSError:
                pass

    @patch("urllib.request.urlopen")
    def test_llm_client_retry_and_success(self, mock_urlopen) -> None:
        """Tests that llm_client retries once on malformed JSON and succeeds on 2nd attempt."""
        mock_response1 = MagicMock()
        mock_response1.__enter__.return_value = mock_response1
        mock_response1.read.return_value = b'{"choices": [{"message": {"content": "not-a-json"}}]}'
        
        mock_response2 = MagicMock()
        mock_response2.__enter__.return_value = mock_response2
        mock_response2.read.return_value = b'{"choices": [{"message": {"content": "{\\"status\\": \\"ok\\"}"}}], "usage": {}}'
        
        # urlopen will return mock_response1 first, then mock_response2
        mock_urlopen.side_effect = [mock_response1, mock_response2]

        result = call_llm(self.case_id, "hello", "test_prompt.txt", response_json_mode=True)
        self.assertEqual(result, '{"status": "ok"}')
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_llm_client_failure_after_two_attempts(self, mock_urlopen) -> None:
        """Tests that llm_client raises RuntimeError if it fails twice."""
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = b'{"choices": [{"message": {"content": "not-a-json"}}]}'
        mock_urlopen.return_value = mock_response

        with self.assertRaises(RuntimeError):
            call_llm(self.case_id, "hello", "test_prompt.txt", response_json_mode=True)
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("agents.bridge.llm_client.call_llm")
    def test_evidence_extractor_schema_missing_fields(self, mock_call_llm) -> None:
        """Tests that missing required schema fields in LLM response raises KeyError."""
        state = CaseState(case_id=self.case_id)
        state.raw_evidence = {
            "declaration": "raw declaration",
            "cnic_scan": "raw cnic",
            "salary_slip": "raw slip",
            "registry_lookup": "raw registry",
            "whatsapp_forward": "raw wa"
        }

        # Return incomplete declaration JSON
        mock_call_llm.return_value = json.dumps({
            "name": "Ahmed Khan",
            "cnic": "42101-2222222-3"
            # Missing other fields
        })

        with self.assertRaises(KeyError):
            extract_evidence(state)

    @patch("agents.bridge.llm_client.call_llm")
    def test_evidence_extractor_invalid_types(self, mock_call_llm) -> None:
        """Tests that invalid types (non-integer household_size) raise TypeError."""
        state = CaseState(case_id=self.case_id)
        state.raw_evidence = {
            "declaration": "raw declaration",
            "cnic_scan": "raw cnic",
            "salary_slip": "raw slip",
            "registry_lookup": "raw registry",
            "whatsapp_forward": "raw wa"
        }

        # Return declaration JSON with string value for household_size that cannot convert
        mock_call_llm.return_value = json.dumps({
            "name": "Ahmed Khan",
            "cnic": "42101-2222222-3",
            "district": "Karachi",
            "household_size": "three-people",  # Invalid number
            "other_earners_declared": False,
            "self_declared_income_pkr": 42000,
            "signed": True,
            "signature_date": "16/06/2026"
        })

        with self.assertRaises(TypeError):
            extract_evidence(state)

    @patch("agents.bridge.llm_client.call_llm")
    def test_extractor_validator_catches_hallucinations(self, mock_call_llm) -> None:
        """Tests that Extraction Validator catches LLM hallucinations (values not in source)."""
        state = CaseState(case_id=self.case_id)
        state.raw_evidence = {
            "declaration": "Name: Ahmed Khan\nCNIC: 42101-2222222-3\nDistrict: Karachi",
            "cnic_scan": "Ahmed Khan, CNIC 42101-2222222-3, valid",
            "salary_slip": "Gross: PKR 44,000\nNet: PKR 40,800",
            "registry_lookup": "identity_verified: true\nregistry_status: ACTIVE",
            "whatsapp_forward": "No instructions"
        }

        def mock_llm_impl(c_id, prompt, prompt_version, response_json_mode=True):
            if "Document Type: declaration" in prompt:
                return json.dumps({
                    "name": "Ahmed Khan",
                    "cnic": "42101-2222222-3",
                    "district": "Lahore",  # Hallucinated! (Karachi in raw)
                    "household_size": 3,
                    "other_earners_declared": False,
                    "self_declared_income_pkr": 42000,
                    "signed": True,
                    "signature_date": "16/06/2026"
                })
            elif "Document Type: cnic_scan" in prompt:
                return json.dumps({"name": "Ahmed Khan", "cnic": "42101-2222222-3", "valid": True})
            elif "Document Type: salary_slip" in prompt:
                return json.dumps({"employer": "KPT", "gross_income_pkr": 44000, "deductions_pkr": 3200, "net_income_pkr": 40800})
            elif "Document Type: registry_lookup" in prompt:
                return json.dumps({"identity_verified": True, "registry_status": "ACTIVE", "flags": [], "active_grants_other_districts": [], "coverage_note": "ok"})
            elif "whatsapp_analysis.txt" in prompt_version:
                return json.dumps({"contains_explicit_applicant_exception_request": False, "contains_third_party_pressure": False, "contains_coordinator_instruction": False, "ignored_note": ""})
            return "{}"

        mock_call_llm.side_effect = mock_llm_impl

        # Run extraction & validation stages
        state = extract_evidence(state)
        state = validate_extraction(state)
        state = validate_evidence(state)

        # Extraction validation should fail for declaration.district
        self.assertFalse(state.extraction_validation["validation_passed"])
        self.assertFalse(state.extraction_validation["fields"]["declaration.district"])
        
        # Overall evidence completeness must be False due to the validation failure
        self.assertFalse(state.validated_evidence["evidence_complete"])

    @patch("agents.bridge.llm_client.call_llm")
    def test_whatsapp_classification_intent_routing(self, mock_call_llm) -> None:
        """Tests that WhatsApp classification flags are processed by Conflict Resolver."""
        state = CaseState(case_id=self.case_id)
        state.raw_evidence = {
            "declaration": "Name: Ahmed Khan",
            "cnic_scan": "Ahmed Khan",
            "salary_slip": "Gross: PKR 44,000",
            "registry_lookup": "ACTIVE",
            "whatsapp_forward": "some text"
        }

        def mock_llm_impl(c_id, prompt, prompt_version, response_json_mode=True):
            if "whatsapp_analysis.txt" in prompt_version:
                # Mock coordinator pressure flag true
                return json.dumps({
                    "contains_explicit_applicant_exception_request": True,
                    "contains_third_party_pressure": False,
                    "contains_coordinator_instruction": True,
                    "ignored_note": "District coordinator wants special verification check"
                })
            elif "Document Type: declaration" in prompt:
                return json.dumps({"name": "Ahmed Khan", "cnic": "42101-2222222-3", "district": "Karachi", "household_size": 3, "other_earners_declared": False, "self_declared_income_pkr": 42000, "signed": True, "signature_date": "16/06/2026"})
            elif "Document Type: cnic_scan" in prompt:
                return json.dumps({"name": "Ahmed Khan", "cnic": "42101-2222222-3", "valid": True})
            elif "Document Type: salary_slip" in prompt:
                return json.dumps({"employer": "KPT", "gross_income_pkr": 44000, "deductions_pkr": 3200, "net_income_pkr": 40800})
            elif "Document Type: registry_lookup" in prompt:
                return json.dumps({"identity_verified": True, "registry_status": "ACTIVE", "flags": [], "active_grants_other_districts": [], "coverage_note": "ok"})
            return "{}"

        mock_call_llm.side_effect = mock_llm_impl

        state = extract_evidence(state)
        state = validate_extraction(state)
        state = validate_evidence(state)
        state = resolve_conflicts(state)

        # Resolver should consume structured exception request flag
        self.assertTrue(state.evidence_summary["explicit_exception_request"])
        
        # Coordinator instruction should end up in ignored_informal_notes list
        ignored = state.evidence_summary["ignored_informal_notes"]
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0]["note"], "District coordinator wants special verification check")

    @patch("agents.bridge.llm_client.call_llm")
    def test_decision_explanation_generation(self, mock_call_llm) -> None:
        """Tests that Decision Explanation Agent calls LLM with structured facts."""
        state = CaseState(case_id=self.case_id)
        state.rule_trace = {
            "rules_fired": ["R5"],
            "verifier_decision": "REJECT_INELIGIBLE_INCOME"
        }
        state.evidence_summary = {
            "evidence_complete": True,
            "ignored_informal_notes": []
        }
        state.decision_validation = {
            "consistent_with_rule_trace": True
        }

        mock_call_llm.return_value = "Verified income is too high."

        state = explain_decision(state)

        # Verify calls were grounded and called with decision_explainer.txt
        mock_call_llm.assert_called_once()
        self.assertEqual(mock_call_llm.call_args[0][2], "decision_explainer.txt")
        self.assertEqual(state.decision_record["explanation"], "Verified income is too high.")
