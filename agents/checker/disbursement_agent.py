"""Module for the consolidated Disbursement Agent (Checker)."""

from datetime import timezone
import datetime as dt_module
import os

from state.case_state import CaseState
from shared.platform import case_trail_dir, read_json, repo_root_from, write_json


def run_disbursement_agent(case_state: CaseState) -> CaseState:
    """Disbursement Agent.

    The checker only sees sanitized findings, so it can safely manage pool
    depletion, transactions, and the public roll without raw PII exposure.
    """
    # Idempotency check
    if hasattr(case_state, "pool_decision") and case_state.pool_decision:
        return case_state

    repo_root = repo_root_from(__file__)
    trail_dir = case_trail_dir(repo_root, case_state.case_id)
    os.makedirs(trail_dir, exist_ok=True)

    thresholds_path = os.path.join(repo_root, "policy", "thresholds.json")
    if not os.path.exists(thresholds_path):
        raise FileNotFoundError(f"Thresholds policy file not found: {thresholds_path}")

    thresholds = read_json(thresholds_path, {})

    starting_pool = thresholds["starting_pool_pkr"]
    min_to_disburse = thresholds["minimum_pool_to_disburse_pkr"]
    grant_amount = thresholds["grant_amount_pkr"]

    pool_state_path = os.path.join(repo_root, "state", "pool_state.json")
    pool_state = read_json(pool_state_path, {"current_balance_pkr": starting_pool, "history": []})

    current_balance = pool_state["current_balance_pkr"]
    findings = case_state.sanitized_findings
    verifier_decision = findings.get("verifier_decision")

    resolved_from_pending = False
    pool_before = current_balance
    pool_after = current_balance

    if verifier_decision == "PENDING_R6_R7":
        resolved_from_pending = True
        if current_balance >= min_to_disburse:
            final_decision = "DISBURSE"
            pool_after = current_balance - grant_amount
        else:
            final_decision = "REJECT_POOL_EXHAUSTED"
    else:
        final_decision = verifier_decision

    pool_decision = {
        "final_decision": final_decision,
        "pool_before": pool_before,
        "pool_after": pool_after,
        "resolved_from_pending": resolved_from_pending
    }
    case_state.pool_decision = pool_decision

    history_entry = {
        "case_id": case_state.case_id,
        "verifier_decision": "RESOLVED" if verifier_decision == "PENDING_R6_R7" else verifier_decision,
        "pool_decision": final_decision,
        "pool_before": pool_before,
        "pool_after": pool_after,
        "timestamp": dt_module.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    pool_state["current_balance_pkr"] = pool_after
    pool_state["history"].append(history_entry)

    write_json(pool_state_path, pool_state)

    write_json(os.path.join(trail_dir, "13_pool_decision.json"), pool_decision)

    codes_path = os.path.join(repo_root, "policy", "decision_codes.json")
    decision_codes = read_json(codes_path, {})

    reverse_codes = {v: k for k, v in decision_codes.items()}
    final_decision_code = reverse_codes[final_decision]

    if final_decision == "DISBURSE":
        disbursing_action = "COMMITTED"
        amount_pkr = grant_amount
    else:
        disbursing_action = "NONE"
        amount_pkr = 0

    transaction = {
        "case_ref": case_state.case_id,
        "final_decision_code": final_decision_code,
        "disbursing_action": disbursing_action,
        "amount_pkr": amount_pkr
    }
    case_state.transaction = transaction

    write_json(os.path.join(trail_dir, "14_transaction.json"), transaction)

    # --- Part 3: Public Roll Append (15_public_roll_entry.json) ---
    if disbursing_action == "COMMITTED":
        entry = {
            "case_ref": transaction["case_ref"],
            "amount_pkr": transaction["amount_pkr"]
        }

        allowed_keys = {"case_ref", "amount_pkr"}
        if set(entry.keys()) != allowed_keys:
            raise ValueError("PII Leakage Prevention: Roll entry contains invalid/prohibited fields.")

        roll_path = os.path.join(repo_root, "outputs", "public_roll.json")
        roll = read_json(roll_path, [])

        roll.append(entry)

        write_json(roll_path, roll)

        case_state.public_roll_entry = entry
    else:
        case_state.public_roll_entry = None

    write_json(os.path.join(trail_dir, "15_public_roll_entry.json"), case_state.public_roll_entry)

    results_path = os.path.join(repo_root, "outputs", "results.json")
    existing_results = read_json(results_path, {"cases": [], "public_roll": []})
    case_entry = {
        "case_id": case_state.case_id,
        "verifier_decision": final_decision,
        "disbursing_action": disbursing_action,
        "pool_before": pool_before,
        "pool_after": pool_after,
        "rules_fired": [final_decision_code]
    }

    cases = [item for item in existing_results.get("cases", []) if item.get("case_id") != case_state.case_id]
    cases.append(case_entry)
    cases.sort(key=lambda item: item.get("case_id", ""))

    write_json(results_path, {
        "cases": cases,
        "public_roll": read_json(os.path.join(repo_root, "outputs", "public_roll.json"), []),
    })

    summary_path = os.path.join(repo_root, "outputs", "run_summary.json")
    processed_refs = {item["case_id"] for item in cases}
    successful_count = len(cases)

    artifact_count = 0
    trail_dir_root = os.path.join(repo_root, "evidence_trail")
    for cid in processed_refs:
        case_trail = os.path.join(trail_dir_root, cid)
        if os.path.exists(case_trail):
            for i in range(1, 16):
                prefix = f"{i:02d}_"
                for name in os.listdir(case_trail):
                    if name.startswith(prefix):
                        artifact_count += 1
                        break

    run_summary = {
        "cases_processed": len(cases),
        "successful_cases": successful_count,
        "failed_cases": 0,
        "pool_balance_remaining": pool_after,
        "timestamp": dt_module.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifacts_generated": artifact_count
    }

    write_json(summary_path, run_summary)

    return case_state


def manage_pool(case_state: CaseState) -> CaseState:
    """Wrapper mapping manage_pool to consolidated agent."""
    return run_disbursement_agent(case_state)


def manage_transaction(case_state: CaseState) -> CaseState:
    """Wrapper mapping manage_transaction to consolidated agent."""
    return run_disbursement_agent(case_state)


def generate_roll(case_state: CaseState) -> CaseState:
    """Wrapper mapping generate_roll to consolidated agent."""
    return run_disbursement_agent(case_state)
