"""Unit tests for the Milestone 2 Evidence Intelligence Pipeline."""

import sys
import os
# Insert repository root into sys.path to resolve internal package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import shutil
import unittest

from state.case_state import CaseState
from agents.maker.evidence_intelligence_agent import (
    collect_evidence,
    extract_evidence,
    validate_extraction,
    validate_evidence,
    resolve_conflicts,
)


class TestEvidencePipeline(unittest.TestCase):
    """Tests the sequential execution and correctness of all 6 evidence stages."""

    def setUp(self) -> None:
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.trail_dir = os.path.join(self.repo_root, "evidence_trail")
        
        # Start patching LLM calls
        from unittest.mock import patch
        from tests.mock_llm import mock_call_llm_impl
        self.llm_patcher = patch("agents.bridge.llm_client.call_llm", side_effect=mock_call_llm_impl)
        self.llm_patcher.start()
        
        # Clean up any existing trail directories for cases to ensure clean test runs
        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            path = os.path.join(self.trail_dir, case)
            if os.path.exists(path):
                # Clean but preserve the folder structure using gitkeep/init files
                # Actually, deleting the files created by tests is fine
                for f in os.listdir(path):
                    if f.endswith(".json"):
                        try:
                            os.remove(os.path.join(path, f))
                        except PermissionError:
                            pass

    def tearDown(self) -> None:
        self.llm_patcher.stop()

    def _run_pipeline(self, case_id: str) -> CaseState:
        """Helper to run the 5 maker agent functions in sequence."""
        state = CaseState(case_id=case_id)
        state = collect_evidence(state)
        state = extract_evidence(state)
        state = validate_extraction(state)
        state = validate_evidence(state)
        state = resolve_conflicts(state)
        return state

    def _assert_audit_files_exist(self, case_id: str) -> None:
        """Asserts that all six audit trail files exist on disk."""
        case_trail_dir = os.path.join(self.trail_dir, case_id)
        expected_files = [
            "01_collection.json",
            "02_extraction.json",
            "03_extraction_validation.json",
            "04_validation.json",
            "05_conflict_resolution.json",
            "06_summary.json"
        ]
        for filename in expected_files:
            file_path = os.path.join(case_trail_dir, filename)
            self.assertTrue(
                os.path.exists(file_path),
                f"Audit trail file missing: {file_path}"
            )

    def test_case_001_success(self) -> None:
        """Verifies CASE-001 parses and resolves to below threshold."""
        state = self._run_pipeline("CASE-001")
        
        summary = state.evidence_summary
        self.assertTrue(summary["evidence_complete"])
        self.assertEqual(summary["income_side"], "below_threshold")
        self.assertFalse(summary["explicit_exception_request"])
        
        # Verify ignored notes (district coordinator instructions)
        ignored = summary["ignored_informal_notes"]
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0]["source"], "whatsapp_forward")
        self.assertIn("District coordinator said", ignored[0]["note"])

        self._assert_audit_files_exist("CASE-001")

    def test_case_002_success(self) -> None:
        """Verifies CASE-002 parses and resolves to above threshold."""
        state = self._run_pipeline("CASE-002")
        
        summary = state.evidence_summary
        self.assertTrue(summary["evidence_complete"])
        self.assertEqual(summary["income_side"], "above_threshold")
        self.assertFalse(summary["explicit_exception_request"])
        
        # Verify political pressure ignored note
        ignored = summary["ignored_informal_notes"]
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0]["source"], "whatsapp_forward")
        self.assertIn("MNA office called", ignored[0]["note"])

        self._assert_audit_files_exist("CASE-002")

    def test_case_003_success(self) -> None:
        """Verifies CASE-003 parses with explicit exception request and unknown income side."""
        state = self._run_pipeline("CASE-003")
        
        summary = state.evidence_summary
        self.assertTrue(summary["evidence_complete"])
        # Both gross (52,000) and net (48,500) are inside the margin [47,000, 53,000], hence unknown
        self.assertEqual(summary["income_side"], "unknown")
        self.assertTrue(summary["explicit_exception_request"])
        
        # Ensure no coordinator pressure was incorrectly captured
        ignored = summary["ignored_informal_notes"]
        self.assertEqual(len(ignored), 0)

        self._assert_audit_files_exist("CASE-003")


if __name__ == "__main__":
    unittest.main()
