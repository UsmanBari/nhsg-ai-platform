"""Central client for managing secure, deterministic LLM invocations and audit logging."""

import os
import json
import urllib.request
import urllib.error
import time
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict


def call_llm(case_id: str, prompt: str, prompt_version: str, response_json_mode: bool = True) -> str:
    """Invokes the LLM with the provided prompt and logs request details.

    Implements a single retry on malformed outputs or HTTP failure.
    Raises explicit exceptions on persistent failures.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("Groq API Key is missing or empty. Please set the GROQ_API_KEY environment variable.")

    model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }
    if response_json_mode:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload).encode("utf-8")
    last_err = None

    for attempt in range(2):
        start_time = time.perf_counter()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = response.read().decode("utf-8")
                resp_json = json.loads(resp_data)

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            content = resp_json["choices"][0]["message"]["content"]
            usage = resp_json.get("usage", {})

            # Clean and validate JSON response if JSON mode is requested
            if response_json_mode:
                stripped_content = content.strip()
                if stripped_content.startswith("```"):
                    # Extract only the JSON portion from markdown fences
                    start_idx = stripped_content.find("{")
                    end_idx = stripped_content.rfind("}")
                    if start_idx != -1 and end_idx != -1:
                        stripped_content = stripped_content[start_idx:end_idx + 1]

                json.loads(stripped_content)  # Verify parse
                content = stripped_content

            _log_llm_call(case_id, model, prompt_version, prompt, content, usage, latency_ms)
            return content

        except Exception as e:
            last_err = e
            # Small delay before retry
            time.sleep(0.5)

    raise RuntimeError(f"LLM invocation failed after 2 attempts. Last error: {last_err}")


def _log_llm_call(case_id: str, model: str, prompt_version: str, prompt_input: str, response_output: str, token_usage: Dict[str, Any], latency_ms: float) -> None:
    """Appends LLM request hashes, model name, and performance metadata to audit file."""
    repo_root = os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
    trail_dir = os.path.join(repo_root, "evidence_trail", case_id)
    os.makedirs(trail_dir, exist_ok=True)
    log_file = os.path.join(trail_dir, "llm_audit_log.json")

    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    input_hash = hashlib.sha256(prompt_input.encode("utf-8")).hexdigest()
    output_hash = hashlib.sha256(response_output.encode("utf-8")).hexdigest()

    entry = {
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "prompt_version": prompt_version,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "token_usage": token_usage,
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None
    }
    logs.append(entry)

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)
