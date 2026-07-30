"""End-to-end integration tests for the nhsg-ai-platform system orchestrator."""

import sys
import os
# Insert repository root into sys.path to resolve internal package imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import unittest
from unittest.mock import patch
import datetime
import hashlib

from main import main


class MockDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        # Return a fixed datetime object for byte-identical comparisons
        return datetime.datetime(2026, 7, 30, 8, 0, 0, tzinfo=tz or datetime.timezone.utc)


class TestEndToEndPipeline(unittest.TestCase):
    """End-to-end orchestration, output validation, and determinism check."""

    def setUp(self) -> None:
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.state_dir = os.path.join(self.repo_root, "state")
        self.outputs_dir = os.path.join(self.repo_root, "outputs")
        self.trail_dir = os.path.join(self.repo_root, "evidence_trail")

        # Robustly clean run-level outputs/states to guarantee clean initial setup
        for path in [
            os.path.join(self.state_dir, "pool_state.json"),
            os.path.join(self.outputs_dir, "public_roll.json"),
            os.path.join(self.outputs_dir, "results.json"),
            os.path.join(self.outputs_dir, "run_summary.json")
        ]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

        # Start patching LLM calls
        from unittest.mock import patch
        from tests.mock_llm import mock_call_llm_impl
        self.llm_patcher = patch("agents.bridge.llm_client.call_llm", side_effect=mock_call_llm_impl)
        self.llm_patcher.start()

        # Robustly clean files 12 to 15
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

    def _read_json(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_file_hash(self, path: str) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def test_e2e_orchestration_flow(self) -> None:
        """Runs the orchestrator and verifies all final deliverables, decisions, and formats."""
        # Execute orchestrator
        main()

        # Check deliverables exist
        results_path = os.path.join(self.outputs_dir, "results.json")
        roll_path = os.path.join(self.outputs_dir, "public_roll.json")
        summary_path = os.path.join(self.outputs_dir, "run_summary.json")
        pool_state_path = os.path.join(self.state_dir, "pool_state.json")

        self.assertTrue(os.path.exists(results_path))
        self.assertTrue(os.path.exists(roll_path))
        self.assertTrue(os.path.exists(summary_path))
        self.assertTrue(os.path.exists(pool_state_path))

        # 1. Assert exactly three cases processed in summary
        summary = self._read_json(summary_path)
        self.assertEqual(summary["cases_processed"], 3)
        self.assertEqual(summary["successful_cases"], 3)
        self.assertEqual(summary["failed_cases"], 0)
        self.assertEqual(summary["pool_balance_remaining"], 54000)

        # 2. Assert results.json contents and decisions
        results_data = self._read_json(results_path)
        cases_list = results_data["cases"]
        self.assertEqual(len(cases_list), 3)

        self.assertEqual(cases_list[0]["case_id"], "CASE-001")
        self.assertEqual(cases_list[0]["verifier_decision"], "DISBURSE")
        self.assertEqual(cases_list[0]["rules_fired"], ["R7"])
        self.assertEqual(cases_list[0]["disbursing_action"], "COMMITTED")

        self.assertEqual(cases_list[1]["case_id"], "CASE-002")
        self.assertEqual(cases_list[1]["verifier_decision"], "REJECT_INELIGIBLE_INCOME")
        self.assertEqual(cases_list[1]["rules_fired"], ["R5"])
        self.assertEqual(cases_list[1]["disbursing_action"], "NONE")

        self.assertEqual(cases_list[2]["case_id"], "CASE-003")
        self.assertEqual(cases_list[2]["verifier_decision"], "ESCALATE_REQUIRES_HUMAN")
        self.assertEqual(cases_list[2]["rules_fired"], ["R4"])
        self.assertEqual(cases_list[2]["disbursing_action"], "NONE")

        # 3. Assert public_roll.json contains exactly one entry (CASE-001)
        roll = self._read_json(roll_path)
        self.assertEqual(len(roll), 1)
        self.assertEqual(roll[0], {"case_ref": "CASE-001", "amount_pkr": 12000})

        # 4. Assert exactly forty-five artifacts exist in total
        artifact_count = 0
        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            case_trail = os.path.join(self.trail_dir, case)
            for i in range(1, 16):
                prefix = f"{i:02d}_"
                for name in os.listdir(case_trail):
                    if name.startswith(prefix):
                        artifact_count += 1
                        break
        self.assertEqual(artifact_count, 45)
        self.assertEqual(summary["artifacts_generated"], 45)

        # 5. Verify no PII appears anywhere in the final artifacts or state files
        prohibited_pii = ["ahmed", "khan", "yasmeen", "akhtar", "muhammad", "ilyas", "42101-2222222-3", "35202-3333333-4", "37405-0101010-1"]
        for path in [results_path, roll_path, summary_path, pool_state_path]:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for pii in prohibited_pii:
                    self.assertNotIn(pii, content, f"PII leakage found in: {path}")

        # 6. Verify sentinel containment (no literal "PENDING_R6_R7" in deliverables)
        for path in [results_path, roll_path, summary_path, pool_state_path]:
            with open(path, "r", encoding="utf-8") as f:
                self.assertNotIn("PENDING_R6_R7", f.read())

    @patch("main.datetime", MockDateTime)
    @patch("agents.maker.verifier_agent.dt_module.datetime", MockDateTime)
    @patch("agents.checker.disbursement_agent.dt_module.datetime", MockDateTime)
    def test_determinism_byte_identical_runs(self) -> None:
        """Verifies that running the orchestrator twice with the same inputs yields byte-identical output files."""
        # --- RUN 1 ---
        main()
        
        # Save hashes of Run 1 outputs and all 45 artifacts
        run1_hashes = {}
        for path in [
            os.path.join(self.outputs_dir, "results.json"),
            os.path.join(self.outputs_dir, "public_roll.json"),
            os.path.join(self.outputs_dir, "run_summary.json"),
            os.path.join(self.state_dir, "pool_state.json")
        ]:
            run1_hashes[path] = self._get_file_hash(path)

        for case in ["CASE-001", "CASE-002", "CASE-003"]:
            case_trail = os.path.join(self.trail_dir, case)
            for name in os.listdir(case_trail):
                if name.endswith(".json"):
                    full_path = os.path.join(case_trail, name)
                    run1_hashes[full_path] = self._get_file_hash(full_path)

        # Clean outputs & states to trigger reset identical to setUp
        self.setUp()

        # --- RUN 2 ---
        main()

        # Compare hashes of Run 2 outputs with Run 1
        for path, hash1 in run1_hashes.items():
            self.assertTrue(os.path.exists(path), f"File {path} missing in second run.")
            hash2 = self._get_file_hash(path)
            self.assertEqual(hash1, hash2, f"Byte determinism mismatch found for file: {path}")


if __name__ == "__main__":
    unittest.main()
