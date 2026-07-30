"""Unit tests for the Milestone 3 Decision Intelligence Layer."""

import sys
import os
# Insert repository root into sys.path to resolve internal package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import unittest

from state.case_state import CaseState
from agents.maker.evidence_intelligence_agent import (
    collect_evidence,
    extract_evidence,
    validate_extraction,
    validate_evidence,
    resolve_conflicts,
)
from agents.maker.verifier_agent import (
    check_eligibility,
    select_rules,
    evaluate_rules,
    resolve_decision,
    validate_decision,
    explain_decision,
    generate_findings,
)


class TestDecisionPipeline(unittest.TestCase):
    """Tests the sequential execution and correctness of all Maker-side agents (Milestone 2 & 3)."""

    def setUp(self) -> None:
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.trail_dir = os.path.join(self.repo_root, "evidence_trail")
        
        # Start patching LLM calls
        from unittest.mock import patch
        from tests.mock_llm import mock_call_llm_impl
        self.llm_patcher = patch("agents.bridge.llm_client.call_llm", side_effect=mock_call_llm_impl)
        self.llm_patcher.start()
        
        # Clean up files 07 to 11 from previous runs
        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            path = os.path.join(self.trail_dir, case)
            if os.path.exists(path):
                for fn in [
                    "07_eligibility_check.json",
                    "08_rule_trace.json",
                    "09_decision_validation.json",
                    "10_decision_record.json",
                    "11_findings.json"
                ]:
                    file_path = os.path.join(path, fn)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except PermissionError:
                            pass

    def tearDown(self) -> None:
        self.llm_patcher.stop()

    def _run_milestone2(self, case_id: str) -> CaseState:
        """Runs the Milestone 2 pipeline."""
        state = CaseState(case_id=case_id)
        state = collect_evidence(state)
        state = extract_evidence(state)
        state = validate_extraction(state)
        state = validate_evidence(state)
        state = resolve_conflicts(state)
        return state

    def _run_milestone3(self, state: CaseState) -> CaseState:
        """Runs the Milestone 3 pipeline."""
        state = check_eligibility(state)
        state = select_rules(state)
        state = evaluate_rules(state)
        state = resolve_decision(state)
        state = validate_decision(state)
        state = explain_decision(state)
        state = generate_findings(state)
        return state

    def _read_artifact(self, case_id: str, filename: str) -> dict:
        """Reads a JSON artifact from the evidence trail."""
        path = os.path.join(self.trail_dir, case_id, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_case_001_success(self) -> None:
        """Verifies CASE-001 rule logic (All rules R1-R5 false -> PENDING)."""
        # 1. Run Milestone 2 and snapshot artifacts 01-06
        state = self._run_milestone2("CASE-001")
        m2_snapshots = {
            fn: self._read_artifact("CASE-001", fn)
            for fn in [
                "01_collection.json",
                "02_extraction.json",
                "03_extraction_validation.json",
                "04_validation.json",
                "05_conflict_resolution.json",
                "06_summary.json"
            ]
        }

        # 2. Run Milestone 3
        state = self._run_milestone3(state)

        # 3. Assert rule matching outcomes
        self.assertEqual(state.rule_trace["verifier_decision"], "PENDING_R6_R7")
        self.assertEqual(state.rule_trace["rules_fired"], [])
        
        # Verify all rules evaluated were false
        results = state.rule_trace["results"]
        self.assertEqual(len(results), 5)
        for res in results:
            self.assertFalse(res["matched"])

        # 4. Assert validator check
        self.assertTrue(state.decision_validation["consistent_with_rule_trace"])

        # 5. Assert PII-free findings
        findings = state.findings
        serialized_findings = json.dumps(findings)
        prohibited_pii = ["Ahmed", "Khan", "42101-2222222-3"]
        for pii in prohibited_pii:
            self.assertNotIn(pii.lower(), serialized_findings.lower())

        # 6. Verify audit files exist and Milestone 2 files remain untouched
        for fn in [
            "07_eligibility_check.json",
            "08_rule_trace.json",
            "09_decision_validation.json",
            "10_decision_record.json",
            "11_findings.json"
        ]:
            path = os.path.join(self.trail_dir, "CASE-001", fn)
            self.assertTrue(os.path.exists(path))

        # Check Milestone 2 snapshots haven't changed
        for fn, expected_content in m2_snapshots.items():
            current_content = self._read_artifact("CASE-001", fn)
            self.assertEqual(current_content, expected_content)

    def test_case_002_success(self) -> None:
        """Verifies CASE-002 rule logic (R1-R4 false, R5 true -> REJECT_INELIGIBLE_INCOME)."""
        state = self._run_milestone2("CASE-002")
        state = self._run_milestone3(state)

        # R5 is income above threshold, which fires
        self.assertEqual(state.rule_trace["verifier_decision"], "REJECT_INELIGIBLE_INCOME")
        self.assertEqual(state.rule_trace["rules_fired"], ["R5"])

        results = state.rule_trace["results"]
        # Verify first four false, fifth true
        for i in range(4):
            self.assertFalse(results[i]["matched"])
        self.assertTrue(results[4]["matched"])

        self.assertTrue(state.decision_validation["consistent_with_rule_trace"])

        # Assert no PII leaks
        serialized_findings = json.dumps(state.findings)
        prohibited_pii = ["Yasmeen", "Akhtar", "35202-3333333-4"]
        for pii in prohibited_pii:
            self.assertNotIn(pii.lower(), serialized_findings.lower())

        # Check audit trail artifacts
        for fn in [
            "07_eligibility_check.json",
            "08_rule_trace.json",
            "09_decision_validation.json",
            "10_decision_record.json",
            "11_findings.json"
        ]:
            path = os.path.join(self.trail_dir, "CASE-002", fn)
            self.assertTrue(os.path.exists(path))

    def test_case_003_success(self) -> None:
        """Verifies CASE-003 rule logic (R1-R3 false, R4 true -> ESCALATE_REQUIRES_HUMAN)."""
        state = self._run_milestone2("CASE-003")
        state = self._run_milestone3(state)

        # R4 is exception request, which fires
        self.assertEqual(state.rule_trace["verifier_decision"], "ESCALATE_REQUIRES_HUMAN")
        self.assertEqual(state.rule_trace["rules_fired"], ["R4"])

        results = state.rule_trace["results"]
        # Verify first three false, fourth true
        for i in range(3):
            self.assertFalse(results[i]["matched"])
        self.assertTrue(results[3]["matched"])

        self.assertTrue(state.decision_validation["consistent_with_rule_trace"])

        # Assert no PII leaks
        serialized_findings = json.dumps(state.findings)
        prohibited_pii = ["Muhammad", "Ilyas", "37405-0101010-1"]
        for pii in prohibited_pii:
            self.assertNotIn(pii.lower(), serialized_findings.lower())

        # Check audit trail artifacts
        for fn in [
            "07_eligibility_check.json",
            "08_rule_trace.json",
            "09_decision_validation.json",
            "10_decision_record.json",
            "11_findings.json"
        ]:
            path = os.path.join(self.trail_dir, "CASE-003", fn)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
