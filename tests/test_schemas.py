"""Unit tests for system schema structures.

Validates that JSON schemas exist, are well-formed, and that sensitive schemas
do not contain PII fields (name, CNIC, address).
"""

import json
import os
import unittest


class TestSchemas(unittest.TestCase):
    """Verifies correctness and PII-safety of JSON schemas."""

    def setUp(self) -> None:
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.schema_dir = os.path.join(self.root_dir, "schemas")

    def test_case_state_schema(self) -> None:
        """Verifies case state schema file exists and is valid JSON."""
        path = os.path.join(self.schema_dir, "case_state.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            data = json.load(f)
        self.assertIn("case_id", data)
        self.assertIn("raw_evidence", data)
        self.assertIn("extracted_evidence", data)

    def test_findings_schema_pii_free(self) -> None:
        """Verifies findings schema is valid and does not contain PII fields."""
        path = os.path.join(self.schema_dir, "findings.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            data = json.load(f)

        # Ensure no standard PII keys are defined at top-level or flags level
        keys = list(data.keys())
        if "flags" in data and isinstance(data["flags"], dict):
            keys.extend(data["flags"].keys())

        prohibited = ["name", "cnic", "address", "phone", "email"]
        for key in keys:
            for p in prohibited:
                self.assertNotIn(p, key.lower(), f"PII key '{key}' found in findings schema")

    def test_public_roll_schema_pii_free(self) -> None:
        """Verifies public roll schema does not contain PII fields."""
        path = os.path.join(self.schema_dir, "public_roll.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            data = json.load(f)

        keys = list(data.keys())
        prohibited = ["name", "cnic", "address", "phone", "email"]
        for key in keys:
            for p in prohibited:
                self.assertNotIn(p, key.lower(), f"PII key '{key}' found in public_roll schema")

    def test_decision_record_schema_pii_free(self) -> None:
        """Verifies decision record schema does not contain PII fields."""
        path = os.path.join(self.schema_dir, "decision_record.json")
        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            data = json.load(f)

        keys = list(data.keys())
        if "engineering_confidence" in data and isinstance(data["engineering_confidence"], dict):
            keys.extend(data["engineering_confidence"].keys())

        prohibited = ["name", "cnic", "address", "phone", "email"]
        for key in keys:
            for p in prohibited:
                self.assertNotIn(p, key.lower(), f"PII key '{key}' found in decision_record schema")


if __name__ == "__main__":
    unittest.main()
