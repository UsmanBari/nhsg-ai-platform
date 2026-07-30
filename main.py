"""Orchestration entrypoint for the nhsg-ai-platform benefit-disbursement system.

This module drives the CaseState sequentially through the consolidated 4-agent pipeline:
  1. Evidence Intelligence Agent (Maker): Performs parsing, completeness checking,
     and LLM-based contradictions and disregarded notes analysis.
  2. Verifier Agent (Verifier): Performs eligibility evaluation and deterministic
     policy checks, followed by LLM structured explanations of outcomes.
  3. PII Sanitizer Agent (Bridge): Inspects findings at the security boundary to
     ensure zero names or CNICs cross over to the Checker.
  4. Disbursement Agent (Checker): Manages pool depletion and commits roll entries.
"""

import json
import os
from datetime import datetime, timezone

from state.case_state import CaseState
from agents.maker.evidence_intelligence_agent import run_evidence_intelligence
from agents.maker.verifier_agent import run_verifier_agent
from agents.bridge.pii_sanitizer import sanitize_pii
from agents.checker.disbursement_agent import run_disbursement_agent


def main() -> None:
    """Orchestrate case state processing across all 4 production-grade agents."""
    repo_root = os.path.dirname(os.path.abspath(__file__))

    # 1. Reset run-level outputs and state to ensure clean run
    pool_state_path = os.path.join(repo_root, "state", "pool_state.json")
    public_roll_path = os.path.join(repo_root, "outputs", "public_roll.json")
    results_path = os.path.join(repo_root, "outputs", "results.json")
    summary_path = os.path.join(repo_root, "outputs", "run_summary.json")

    for path in [pool_state_path, public_roll_path, results_path, summary_path]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except PermissionError:
                pass

    # Reset per-case audit files 12-15 to ensure clean numbers
    trail_dir = os.path.join(repo_root, "evidence_trail")
    for case in ["CASE-001", "CASE-002", "CASE-003"]:
        case_trail = os.path.join(trail_dir, case)
        if os.path.exists(case_trail):
            for fn in [
                "12_sanitized_findings.json",
                "13_pool_decision.json",
                "14_transaction.json",
                "15_public_roll_entry.json"
            ]:
                file_path = os.path.join(case_trail, fn)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except PermissionError:
                        pass

    cases = ["CASE-001", "CASE-002", "CASE-003"]
    successful_count = 0
    failed_count = 0

    for case_id in cases:
        try:
            # Initialize CaseState containing the case identifier
            state = CaseState(case_id=case_id)
            
            # --- STAGE 1: Evidence Intelligence Agent (Maker) ---
            # Loads raw fixtures, parses them deterministically, classifications WhatsApp intents via LLM,
            # runs completeness and extraction validations, compiles disregarded notes, and summarizes via LLM.
            state = run_evidence_intelligence(state)

            # --- STAGE 2: Verifier Agent (Verifier) ---
            # Evaluates eligibility parameters, runs deterministic rule matches R1-R5, resolves the decision,
            # verifies with an independent validator re-checker, and explains the outcome via LLM.
            state = run_verifier_agent(state)

            # --- STAGE 3: PII Sanitizer Agent (Secure Bridge Boundary) ---
            # Enforces unidirectional flow: inspects findings keys and values, halting loudly on any names/CNICs.
            state = sanitize_pii(state)

            # --- STAGE 4: Disbursement Agent (Checker) ---
            # Adjusts running pool balance, commits transactions, appends roll entries, and updates outputs.
            state = run_disbursement_agent(state)

            successful_count += 1
        except Exception as e:
            failed_count += 1
            print(f"Error processing {case_id}: {e}")

    # Display execution report on CLI console
    results_cases = []
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            try:
                results_data = json.load(f)
                if isinstance(results_data, dict):
                    results_cases = results_data.get("cases", [])
                elif isinstance(results_data, list):
                    results_cases = results_data
            except Exception:
                pass

    thresholds_path = os.path.join(repo_root, "policy", "thresholds.json")
    starting_pool = 0
    grant_amount = 0
    if os.path.exists(thresholds_path):
        with open(thresholds_path, "r", encoding="utf-8") as f:
            thresholds = json.load(f)
            starting_pool = thresholds.get("starting_pool_pkr", 0)
            grant_amount = thresholds.get("grant_amount_pkr", 0)

    if os.path.exists(pool_state_path):
        with open(pool_state_path, "r", encoding="utf-8") as f:
            pool_data = json.load(f)
            final_balance = pool_data.get("current_balance_pkr", starting_pool)
    else:
        final_balance = starting_pool

    disbursed_text = ""
    rejected_text = ""
    escalated_text = ""

    for res in results_cases:
        # Fallback if case elements have slightly different names in older formats
        ref = res.get("case_id") or res.get("case_ref")
        dec = res.get("verifier_decision") or res.get("decision")
        action = res.get("disbursing_action") or ("COMMITTED" if dec == "DISBURSE" else "NONE")
        amt = grant_amount if action == "COMMITTED" else 0
        if action == "COMMITTED":
            disbursed_text += f"{ref} -> PKR {amt:,}\n"
        elif dec.startswith("REJECT"):
            rejected_text += f"{ref}\n"
        elif dec.startswith("ESCALATE"):
            escalated_text += f"{ref}\n"

    print("=======================================")
    print("NHSG AI PLATFORM - 4 AGENT ARCHITECTURE")
    print("Execution Complete")
    print("=======================================")
    print(f"\nCases Processed: {len(cases)}")
    print(f"Successful: {successful_count}")
    print(f"Failed: {failed_count}")
    print(f"\nFinal Pool Balance:\nPKR {final_balance:,}")
    print(f"\nDisbursed:\n{disbursed_text.strip()}")
    print(f"\nRejected:\n{rejected_text.strip()}")
    print(f"\nEscalated:\n{escalated_text.strip()}")


if __name__ == "__main__":
    main()
