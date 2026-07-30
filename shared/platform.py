"""Shared platform helpers for paths, parsing, validation, and PII checks."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable


CNIC_PATTERN = re.compile(r"\d{5}-\d{7}-\d")
PROHIBITED_PII_KEYS = {"name", "cnic", "address", "phone", "email"}


def repo_root_from(path: str) -> str:
    current = os.path.abspath(path)
    for _ in range(6):
        if os.path.exists(os.path.join(current, "policy")) and os.path.exists(os.path.join(current, "prompts")):
            return current
        current = os.path.dirname(current)
    # Fallback
    current = os.path.abspath(path)
    for _ in range(3):
        current = os.path.dirname(current)
    return current


def case_trail_dir(repo_root: str, case_id: str) -> str:
    return os.path.join(repo_root, "evidence_trail", case_id)


def fixture_path(repo_root: str, case_id: str) -> str:
    filename = f"{case_id.lower().replace('-', '_')}.json"
    return os.path.join(repo_root, "tests", "fixtures", filename)


def read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def parse_declaration(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for line in [line.strip() for line in text.splitlines()]:
        if line.startswith("Name"):
            match = re.match(r"Name\s*\.+\s*(.*)", line)
            if match:
                result["name"] = match.group(1).strip()
        elif line.startswith("CNIC"):
            match = re.match(r"CNIC\s*\.+\s*([\d-]+)", line)
            if match:
                result["cnic"] = match.group(1).strip()
        elif line.startswith("District"):
            match = re.match(r"District\s*\.+\s*(.*)", line)
            if match:
                result["district"] = match.group(1).strip()
        elif line.startswith("Household size"):
            match = re.match(r"Household size\s*\.+\s*(\d+)", line)
            if match:
                result["household_size"] = int(match.group(1))
        elif line.startswith("Other earning members?") or line.startswith("Other earners?"):
            match = re.match(r"Other\s+(?:earning\s+members|earners)\?\s*\.+\s*(YES|NO)", line, re.IGNORECASE)
            if match:
                result["other_earners_declared"] = match.group(1).upper() == "YES"
        elif line.startswith("Monthly income"):
            match = re.match(r"Monthly income\s*\.+\s*(Rs\.\s*)?([\d,]+)", line, re.IGNORECASE)
            if match:
                result["self_declared_income_pkr"] = int(match.group(2).replace(",", ""))
        elif line.startswith("Signature"):
            result["signed"] = re.search(r"Signature\s*\.+\s*\[signed\]", line, re.IGNORECASE) is not None
            match = re.search(r"Date\s*\.+\s*([\d/]+)", line)
            if match:
                result["signature_date"] = match.group(1).strip()
    return result


def parse_cnic_scan(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    match = re.search(r"(?:Clear photo:\s*)?([^,]+),\s*CNIC\s+([\d-]+)", text)
    if match:
        result["name"] = match.group(1).strip()
        result["cnic"] = match.group(2).strip()
    else:
        parts = text.split(",")
        if parts:
            result["name"] = parts[0].strip()
        cnic_match = re.search(r"([\d-]+)", text)
        result["cnic"] = cnic_match.group(1).strip() if cnic_match else ""
    result["valid"] = "valid" in text.lower()
    return result


def parse_salary_slip(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for line in [line.strip() for line in text.splitlines()]:
        if "PAY SLIP" in line:
            result["employer"] = line.split("—")[0].strip()
            break
    if "employer" not in result:
        result["employer"] = ""

    gross_match = re.search(r"Gross(?:\s+salary)?\s*\.+\s*(?:PKR\s*)?([\d,]+)", text, re.IGNORECASE)
    ded_match = re.search(r"(?:Less\s+)?deductions\s*\.+\s*(?:PKR\s*)?([\d,]+)", text, re.IGNORECASE)
    net_match = re.search(r"Net(?:\s+pay)?\s*\.+\s*(?:PKR\s*)?([\d,]+)", text, re.IGNORECASE)

    result["gross_income_pkr"] = int(gross_match.group(1).replace(",", "")) if gross_match else 0
    result["deductions_pkr"] = int(ded_match.group(1).replace(",", "")) if ded_match else 0
    result["net_income_pkr"] = int(net_match.group(1).replace(",", "")) if net_match else 0
    return result


def parse_registry_lookup(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for line in text.splitlines():
        if " : " not in line:
            continue
        key, value = line.split(" : ", 1)
        key = key.strip()
        value = value.strip()
        if key == "identity_verified":
            result["identity_verified"] = value.upper() == "TRUE"
        elif key == "registry_status":
            result["registry_status"] = value
        elif key == "flags":
            result["flags"] = [] if value.upper() == "NONE" else [item.strip() for item in value.split(",") if item.strip()]
        elif key == "active_grants_other_districts":
            result["active_grants_other_districts"] = [] if value.upper() == "NONE" else [item.strip() for item in value.split(",") if item.strip()]
        elif key == "coverage_note":
            result["coverage_note"] = value
    return result


def validate_declaration(data: Dict[str, Any]) -> Dict[str, Any]:
    required = ["name", "cnic", "district", "household_size", "other_earners_declared", "self_declared_income_pkr", "signed", "signature_date"]
    for key in required:
        if key not in data:
            raise KeyError(f"Missing required field '{key}' in declaration schema.")
    
    if not isinstance(data["household_size"], int) or isinstance(data["household_size"], bool):
        raise TypeError("household_size must be an integer.")
    if not isinstance(data["self_declared_income_pkr"], int) or isinstance(data["self_declared_income_pkr"], bool):
        raise TypeError("self_declared_income_pkr must be an integer.")

    return {
        "name": str(data["name"]).strip(),
        "cnic": str(data["cnic"]).strip(),
        "district": str(data["district"]).strip(),
        "household_size": int(data["household_size"]),
        "other_earners_declared": bool(data["other_earners_declared"]),
        "self_declared_income_pkr": int(data["self_declared_income_pkr"]),
        "signed": bool(data["signed"]),
        "signature_date": str(data["signature_date"]).strip(),
    }


def validate_cnic_scan(data: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["name", "cnic", "valid"]:
        if key not in data:
            raise KeyError(f"Missing required field '{key}' in cnic_scan schema.")
    return {
        "name": str(data["name"]).strip(),
        "cnic": str(data["cnic"]).strip(),
        "valid": bool(data["valid"]),
    }


def validate_salary_slip(data: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["employer", "gross_income_pkr", "deductions_pkr", "net_income_pkr"]:
        if key not in data:
            raise KeyError(f"Missing required field '{key}' in salary_slip schema.")
            
    for key in ["gross_income_pkr", "deductions_pkr", "net_income_pkr"]:
        if not isinstance(data[key], int) or isinstance(data[key], bool):
            raise TypeError(f"'{key}' must be an integer.")

    return {
        "employer": str(data["employer"]).strip(),
        "gross_income_pkr": int(data["gross_income_pkr"]),
        "deductions_pkr": int(data["deductions_pkr"]),
        "net_income_pkr": int(data["net_income_pkr"]),
    }


def validate_registry_lookup(data: Dict[str, Any]) -> Dict[str, Any]:
    for key in ["identity_verified", "registry_status", "flags", "active_grants_other_districts", "coverage_note"]:
        if key not in data:
            raise KeyError(f"Missing required field '{key}' in registry_lookup schema.")

    flags = data["flags"]
    if isinstance(flags, str):
        flags = [item.strip() for item in flags.split(",") if item.strip()]
    elif not isinstance(flags, list):
        raise TypeError(f"Invalid type for flags: {type(flags)}")

    active = data["active_grants_other_districts"]
    if isinstance(active, str):
        active = [item.strip() for item in active.split(",") if item.strip()]
    elif not isinstance(active, list):
        raise TypeError(f"Invalid type for active_grants_other_districts: {type(active)}")

    return {
        "identity_verified": bool(data["identity_verified"]),
        "registry_status": str(data["registry_status"]).strip(),
        "flags": [str(item) for item in flags],
        "active_grants_other_districts": [str(item) for item in active],
        "coverage_note": str(data["coverage_note"]).strip(),
    }


def present_in_raw(value: Any, raw_text: str) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, int):
        return str(value) in raw_text or f"{value:,}" in raw_text
    if isinstance(value, str):
        return value in raw_text
    return False


def contains_pii(value: Any, pii_tokens: Iterable[str] = ()) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        if CNIC_PATTERN.search(value):
            return True
        return any(token and token.lower() in lowered for token in pii_tokens)
    if isinstance(value, dict):
        return any(key.lower() in PROHIBITED_PII_KEYS or contains_pii(key, pii_tokens) or contains_pii(item, pii_tokens) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_pii(item, pii_tokens) for item in value)
    return False


def sanitize_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))
