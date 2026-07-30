"""Unit tests for verifying system policy configurations.

Verifies that the policy values match specifications and that policy constants
are not hardcoded inside Python code.
"""

import json
import os
import unittest


class TestPolicyValues(unittest.TestCase):
    """Verifies correctness of the policy configurations and rules."""

    def setUp(self) -> None:
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.policy_dir = os.path.join(self.root_dir, "policy")

    def test_thresholds_json(self) -> None:
        """Verifies thresholds values match architectural specifications."""
        path = os.path.join(self.policy_dir, "thresholds.json")
        self.assertTrue(os.path.exists(path))

        with open(path, "r") as f:
            data = json.load(f)

        self.assertEqual(data.get("household_income_threshold_pkr"), 50000)
        self.assertEqual(data.get("numeric_margin_pkr"), 3000)
        self.assertEqual(data.get("grant_amount_pkr"), 12000)
        self.assertEqual(data.get("starting_pool_pkr"), 66000)
        self.assertEqual(data.get("minimum_pool_to_disburse_pkr"), 12000)

    def test_decision_codes_json(self) -> None:
        """Verifies decision codes exist and are correctly mapped."""
        path = os.path.join(self.policy_dir, "decision_codes.json")
        self.assertTrue(os.path.exists(path))

        with open(path, "r") as f:
            data = json.load(f)

        expected = {
            "R1": "REJECT_INCOMPLETE_EVIDENCE",
            "R2": "REJECT_NOT_ELIGIBLE",
            "R3": "REJECT_DUPLICATE_CLAIM",
            "R4": "ESCALATE_REQUIRES_HUMAN",
            "R5": "REJECT_INELIGIBLE_INCOME",
            "R6": "REJECT_POOL_EXHAUSTED",
            "R7": "DISBURSE",
        }
        self.assertEqual(data, expected)

    def test_rules_json(self) -> None:
        """Verifies rules structure and evaluation order matches specification."""
        path = os.path.join(self.policy_dir, "rules.json")
        self.assertTrue(os.path.exists(path))

        with open(path, "r") as f:
            data = json.load(f)

        self.assertEqual(
            data.get("evaluation_order"), ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
        )
        rules = data.get("rules", [])
        self.assertEqual(len(rules), 7)
        rule_ids = [r["id"] for r in rules]
        self.assertEqual(rule_ids, ["R1", "R2", "R3", "R4", "R5", "R6", "R7"])

    def test_conflict_resolution_json(self) -> None:
        """Verifies conflict resolution strategies exist."""
        path = os.path.join(self.policy_dir, "conflict_resolution.json")
        self.assertTrue(os.path.exists(path))

        with open(path, "r") as f:
            data = json.load(f)

        self.assertIn("self_declared_vs_verified_income", data)
        self.assertIn("gross_vs_net_income", data)
        self.assertIn("multiple_household_earners", data)
        self.assertIn("informal_notes_chat_forwards", data)
        self.assertIn("explicit_exception_override_requests", data)

    def test_no_hardcoded_policy_numbers_in_source_code(self) -> None:
        """Verifies that none of the thresholds are hardcoded in agent/pipeline Python files."""
        prohibited_numbers = ["50000", "3000", "12000", "66000"]
        
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                if file.endswith(".py"):
                    # Exclude the test suite itself and scratch scripts
                    normalized_path = os.path.join(root, file).replace("\\", "/")
                    if "/tests/" in normalized_path or "create_tree" in file or "create_agent_stubs" in file:
                        continue
                    
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    for num in prohibited_numbers:
                        # Simple substring check to verify no hardcoding of constants
                        # (ignoring comment blocks or strings is possible, but general sanity is good)
                        self.assertNotIn(
                            f" {num}", 
                            content, 
                            f"Hardcoded policy threshold '{num}' found in {normalized_path}"
                        )
                        self.assertNotIn(
                            f"={num}", 
                            content, 
                            f"Hardcoded policy threshold '{num}' found in {normalized_path}"
                        )


if __name__ == "__main__":
    unittest.main()
