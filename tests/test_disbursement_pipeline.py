"""Unit tests for the Milestone 4 bridge and Secure Disbursement Pipeline."""

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

from agents.bridge.pii_sanitizer import sanitize_pii
from agents.checker.disbursement_agent import (
    manage_pool,
    manage_transaction,
    generate_roll,
)


class TestDisbursementPipeline(unittest.TestCase):
    """Tests bridge sanitization, pool balance depletion, and public rolls (Milestones 1-4)."""

    def setUp(self) -> None:
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.state_dir = os.path.join(self.repo_root, "state")
        self.outputs_dir = os.path.join(self.repo_root, "outputs")
        self.trail_dir = os.path.join(self.repo_root, "evidence_trail")

        # Start patching LLM calls
        from unittest.mock import patch
        from tests.mock_llm import mock_call_llm_impl
        self.llm_patcher = patch("agents.bridge.llm_client.call_llm", side_effect=mock_call_llm_impl)
        self.llm_patcher.start()

        # Clean run-level checker files
        for path in [
            os.path.join(self.state_dir, "pool_state.json"),
            os.path.join(self.outputs_dir, "public_roll.json")
        ]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

        # Clean per-case files 12 to 15
        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            path = os.path.join(self.trail_dir, case)
            if os.path.exists(path):
                for fn in [
                    "12_sanitized_findings.json",
                    "13_pool_decision.json",
                    "14_transaction.json",
                    "15_public_roll_entry.json"
                ]:
                    file_path = os.path.join(path, fn)
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except PermissionError:
                            pass

    def tearDown(self) -> None:
        self.llm_patcher.stop()

    def _run_full_pipeline(self, case_id: str) -> CaseState:
        """Runs the entire 16-stage pipeline (all agents implemented so far)."""
        state = CaseState(case_id=case_id)
        state = collect_evidence(state)
        state = extract_evidence(state)
        state = validate_extraction(state)
        state = validate_evidence(state)
        state = resolve_conflicts(state)
        state = check_eligibility(state)
        state = select_rules(state)
        state = evaluate_rules(state)
        state = resolve_decision(state)
        state = validate_decision(state)
        state = explain_decision(state)
        state = generate_findings(state)
        state = sanitize_pii(state)
        state = manage_pool(state)
        state = manage_transaction(state)
        state = generate_roll(state)
        return state

    def _read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_sequential_disbursement_pipeline(self) -> None:
        """Runs CASE-001, CASE-002, CASE-003 sequentially and verifies disbursement stateful logic."""
        # --- CASE-001 ---
        # Capture Milestone 1-3 artifacts content right after M3 run
        m3_state = CaseState(case_id="CASE-001")
        m3_state = collect_evidence(m3_state)
        m3_state = extract_evidence(m3_state)
        m3_state = validate_extraction(m3_state)
        m3_state = validate_evidence(m3_state)
        m3_state = resolve_conflicts(m3_state)
        m3_state = check_eligibility(m3_state)
        m3_state = select_rules(m3_state)
        m3_state = evaluate_rules(m3_state)
        m3_state = resolve_decision(m3_state)
        m3_state = validate_decision(m3_state)
        m3_state = explain_decision(m3_state)
        m3_state = generate_findings(m3_state)

        # Snapshot files 01-11
        m3_snapshots = {}
        for i in range(1, 12):
            fn = f"{i:02d}_"
            # find full name in directory
            case_trail = os.path.join(self.trail_dir, "CASE-001")
            for name in os.listdir(case_trail):
                if name.startswith(fn):
                    m3_snapshots[name] = self._read_json(os.path.join(case_trail, name))

        # Run full pipeline for CASE-001 (resolves PENDING_R6_R7 -> DISBURSE)
        state1 = self._run_full_pipeline("CASE-001")

        self.assertEqual(state1.sanitized_findings["verifier_decision"], "PENDING_R6_R7")
        self.assertEqual(state1.pool_decision["pool_before"], 66000)
        self.assertEqual(state1.pool_decision["pool_after"], 54000)
        self.assertEqual(state1.pool_decision["final_decision"], "DISBURSE")
        self.assertEqual(state1.transaction["disbursing_action"], "COMMITTED")
        self.assertEqual(state1.transaction["amount_pkr"], 12000)
        self.assertEqual(state1.transaction["final_decision_code"], "R7")
        self.assertEqual(state1.public_roll_entry["amount_pkr"], 12000)

        # Check Milestone 2 snapshots haven't changed
        for fn, expected_content in m3_snapshots.items():
            current_content = self._read_json(os.path.join(self.trail_dir, "CASE-001", fn))
            if "10_decision_record.json" in fn:
                expected_content.pop("timestamp", None)
                current_content.pop("timestamp", None)
            self.assertEqual(current_content, expected_content)

        # --- CASE-002 ---
        # Run full pipeline (verifier decision REJECT_INELIGIBLE_INCOME passes through)
        state2 = self._run_full_pipeline("CASE-002")

        self.assertEqual(state2.sanitized_findings["verifier_decision"], "REJECT_INELIGIBLE_INCOME")
        self.assertEqual(state2.pool_decision["final_decision"], "REJECT_INELIGIBLE_INCOME")
        self.assertEqual(state2.pool_decision["pool_before"], 54000)
        self.assertEqual(state2.pool_decision["pool_after"], 54000)
        self.assertEqual(state2.transaction["disbursing_action"], "NONE")
        self.assertIsNone(state2.public_roll_entry)

        # --- CASE-003 ---
        # Run full pipeline (verifier decision ESCALATE_REQUIRES_HUMAN passes through)
        state3 = self._run_full_pipeline("CASE-003")

        self.assertEqual(state3.sanitized_findings["verifier_decision"], "ESCALATE_REQUIRES_HUMAN")
        self.assertEqual(state3.pool_decision["final_decision"], "ESCALATE_REQUIRES_HUMAN")
        self.assertEqual(state3.pool_decision["pool_before"], 54000)
        self.assertEqual(state3.pool_decision["pool_after"], 54000)
        self.assertEqual(state3.transaction["disbursing_action"], "NONE")
        self.assertIsNone(state3.public_roll_entry)

        # --- RUN-LEVEL VERIFICATIONS ---
        # Pool state verification
        pool_state_path = os.path.join(self.state_dir, "pool_state.json")
        pool_state = self._read_json(pool_state_path)
        self.assertEqual(pool_state["current_balance_pkr"], 54000)
        self.assertEqual(len(pool_state["history"]), 3)

        # Public roll verification
        roll_path = os.path.join(self.outputs_dir, "public_roll.json")
        roll = self._read_json(roll_path)
        self.assertEqual(len(roll), 1)
        self.assertEqual(roll[0], {"case_ref": "CASE-001", "amount_pkr": 12000})

        # --- PII SECURITY VERIFICATIONS ---
        prohibited_pii = ["ahmed", "khan", "yasmeen", "akhtar", "muhammad", "ilyas", "42101-2222222-3", "35202-3333333-4", "37405-0101010-1"]
        
        # Verify no PII in public roll or pool state files
        for path in [pool_state_path, roll_path]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for pii in prohibited_pii:
                    self.assertNotIn(pii, content, f"PII leak detected in {path}: {pii}")

        # Verify no PII in checker audit trail files
        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            case_trail = os.path.join(self.trail_dir, case)
            for fn in ["12_sanitized_findings.json", "13_pool_decision.json", "14_transaction.json", "15_public_roll_entry.json"]:
                path = os.path.join(case_trail, fn)
                self.assertTrue(os.path.exists(path))
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    for pii in prohibited_pii:
                        self.assertNotIn(pii, content, f"PII leak detected in {path}: {pii}")

        # --- SENTINEL CONTAINMENT VERIFICATIONS ---
        # "PENDING_R6_R7" must only exist in sanitized_findings, never in pool_decision, transaction, or public roll
        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            case_trail = os.path.join(self.trail_dir, case)
            for fn in ["13_pool_decision.json", "14_transaction.json", "15_public_roll_entry.json"]:
                path = os.path.join(case_trail, fn)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.assertNotIn("PENDING_R6_R7", content, f"Sentinel found in checker file: {path}")

        for path in [pool_state_path, roll_path]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertNotIn("PENDING_R6_R7", content, f"Sentinel found in checkers running state: {path}")

    def test_pii_sanitizer_fails_on_leak(self) -> None:
        """Verifies that PII Sanitizer stops execution if input findings contains name or CNIC."""
        state = CaseState(case_id="CASE-FAIL")
        # Injected name into verifier_decision key/value to trigger Sanitizer fail
        state.findings = {
            "case_ref": "CASE-FAIL",
            "verifier_decision": "PENDING_R6_R7",
            "rules_fired": [],
            "flags": {
                "income_side": "below_threshold",
                "evidence_complete": True,
                "duplicate_flag": False,
                "explicit_exception_request": False
            },
            "leak_field": "Ahmed Khan",  # Name injection
            "decision_record_ref": "10_decision_record.json"
        }
        with self.assertRaises(ValueError):
            sanitize_pii(state)

        # Injected CNIC into verifier_decision key/value to trigger Sanitizer fail
        state.findings = {
            "case_ref": "CASE-FAIL",
            "verifier_decision": "PENDING_R6_R7",
            "rules_fired": [],
            "flags": {
                "income_side": "below_threshold",
                "evidence_complete": True,
                "duplicate_flag": False,
                "explicit_exception_request": False
            },
            "leak_field": "42101-2222222-3",  # CNIC injection
            "decision_record_ref": "10_decision_record.json"
        }
        with self.assertRaises(ValueError):
            sanitize_pii(state)


if __name__ == "__main__":
    unittest.main()
