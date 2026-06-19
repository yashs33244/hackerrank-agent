"""Auto-improvement loop — iteratively refines prompts against ground truth.

Inspired by Karpathy's autoresearch concept: evaluate → identify failures →
generate improved prompt → re-run → repeat.

NOT part of the deliverable. Run from repo root:
    python scripts/improve_loop.py [--iterations N] [--agent router|triage|responder|critic]

Algorithm per iteration:
  1. Run the pipeline on the sample tickets only (faster than full run)
  2. Score output with evaluate.py logic
  3. Identify lowest-scoring tickets
  4. Use a Gemini call to propose a targeted prompt patch
  5. Apply the patch to the prompt file
  6. Repeat until score stops improving or max iterations reached

Improved prompts are written back to code/prompts/*.md.
Each iteration saves a checkpoint in scripts/improve_checkpoints/.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "code"))

from config import settings  # noqa: E402 — must come after sys.path insert
from domain.types import TicketState  # noqa: E402
from pipeline import PipelineFactory  # noqa: E402

_SAMPLE_CSV = settings.paths.sample_csv
_PROMPTS_DIR = settings.paths.prompts_dir
_CHECKPOINTS_DIR = _REPO_ROOT / "scripts" / "improve_checkpoints"

# Import scoring logic from evaluate
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from evaluate import score_row  # noqa: E402

_IMPROVABLE_AGENTS = ("router", "triage", "responder", "critic")

_IMPROVE_SYSTEM_PROMPT = """\
You are a prompt engineer specializing in improving support-ticket classification prompts.

You will receive:
1. The current prompt text for an agent
2. Examples where the agent produced wrong outputs (with ground-truth)

Your task: propose a minimal, surgical edit to the prompt that would fix the
failures without regressing on passing cases.

Output a JSON object:
{
  "analysis": "...",          // what is causing the failures
  "patch": "..."              // the new prompt text (complete file content)
}

IMPORTANT:
- The patch must be the COMPLETE new prompt text, not a diff.
- Make targeted changes only — do not rewrite everything.
- Keep all security guardrails intact.
"""


def _run_pipeline_on_samples(pipeline) -> List[dict]:
    """Run pipeline on sample tickets and return output rows."""
    with _SAMPLE_CSV.open(encoding="utf-8") as fh:
        samples = list(csv.DictReader(fh))

    results = []
    for row in samples:
        state = TicketState(
            ticket=(row.get("Issue") or "").strip(),
            subject=(row.get("Subject") or "").strip(),
            company=(row.get("Company") or "").strip(),
        )
        try:
            output = pipeline.run(state)
            results.append(output.to_dict())
        except Exception as exc:
            results.append({
                "status": "escalated",
                "product_area": "error",
                "response": f"Error: {exc}",
                "justification": "",
                "request_type": "product_issue",
            })
        time.sleep(0.5)  # rate limit buffer

    return results


def _score_run(samples: List[dict], outputs: List[dict]) -> dict:  # type: ignore[override]
    n = min(len(samples), len(outputs))
    rows = [score_row(samples[i], outputs[i]) for i in range(n)]
    total = sum(r["total"] for r in rows)
    max_score = sum(r["max"] for r in rows)
    return {
        "total": total,
        "max": max_score,
        "pct": round(100 * total / max_score, 1) if max_score else 0.0,
        "rows": rows,
    }


def _build_failure_context(samples: List[dict], outputs: List[dict], scores: dict) -> str:
    lines = []
    for i, row in enumerate(scores["rows"]):
        if row["total"] < 3.0:
            s = samples[i]
            o = outputs[i]
            lines.append(
                f"Ticket {i+1}: {s.get('Subject', '')!r}\n"
                f"  Ticket text: {s.get('Issue', '')[:150]}\n"
                f"  Expected: status={row['gt_status']}, area={row['gt_area']}, type={row['gt_type']}\n"
                f"  Got:      status={row['pred_status']}, area={row['pred_area']}, type={row['pred_type']}\n"
                f"  Scores:   {row['total']}/4.0"
            )
    return "\n\n".join(lines) if lines else "No failures found."


def _request_improvement(agent_name: str, current_prompt: str, failure_context: str) -> Optional[str]:
    """Ask Gemini to propose a prompt patch."""
    from agents.gemini_client import GeminiClientFactory
    factory = GeminiClientFactory()
    client = factory.medium()

    user_message = (
        f"Current prompt for {agent_name!r} agent:\n\n"
        f"```\n{current_prompt}\n```\n\n"
        f"Failures to fix:\n\n{failure_context}"
    )

    full = f"{_IMPROVE_SYSTEM_PROMPT}\n\n{user_message}"
    response = client.generate_content([{"role": "user", "parts": [full]}])
    text = response.text

    import re
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        print(f"  Analysis: {data.get('analysis', '')[:200]}")
        return data.get("patch")
    except json.JSONDecodeError:
        return None


def _save_checkpoint(iteration: int, scores: dict, prompt_name: str, prompt_content: str) -> None:
    chk_dir = _CHECKPOINTS_DIR / f"iter_{iteration:02d}"
    chk_dir.mkdir(parents=True, exist_ok=True)
    (chk_dir / "scores.json").write_text(json.dumps(scores, indent=2))
    (chk_dir / f"{prompt_name}.md").write_text(prompt_content)


def run_loop(agent_name: str, max_iterations: int) -> None:
    print(f"\n=== Auto-improvement loop: {agent_name!r} agent | {max_iterations} iterations ===\n")

    with _SAMPLE_CSV.open(encoding="utf-8") as fh:
        samples = list(csv.DictReader(fh))

    prompt_path = _PROMPTS_DIR / f"{agent_name}.md"
    if not prompt_path.exists():
        print(f"ERROR: prompt not found: {prompt_path}")
        return

    best_score: Optional[float] = None
    best_prompt: Optional[str] = None

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- Iteration {iteration} ---")

        # Rebuild pipeline fresh (picks up any prompt changes)
        pipeline = PipelineFactory.create()
        outputs = _run_pipeline_on_samples(pipeline)
        scores = _score_run(samples, outputs)

        print(f"Score: {scores['total']:.2f}/{scores['max']:.1f}  ({scores['pct']}%)")

        current_prompt = prompt_path.read_text(encoding="utf-8")
        _save_checkpoint(iteration, scores, agent_name, current_prompt)

        if best_score is None or scores["total"] > best_score:
            best_score = scores["total"]
            best_prompt = current_prompt
            print(f"  → New best score!")

        # Check for convergence
        if scores["pct"] >= 95.0:
            print("  → Converged at ≥95%. Stopping.")
            break

        # Generate improvement
        failure_context = _build_failure_context(samples, outputs, scores)
        if "No failures found" in failure_context:
            print("  → No failures to fix. Stopping.")
            break

        print("  Requesting improvement from LLM…")
        new_prompt = _request_improvement(agent_name, current_prompt, failure_context)
        if not new_prompt:
            print("  → Could not parse improvement. Skipping iteration.")
            continue

        # Backup and apply
        shutil.copy(prompt_path, prompt_path.with_suffix(".md.bak"))
        prompt_path.write_text(new_prompt, encoding="utf-8")
        print("  Prompt updated. Re-running pipeline next iteration…")
        time.sleep(2)

    print(f"\nLoop complete. Best score: {best_score:.2f}")
    if best_prompt:
        print("Best prompt is saved in the latest checkpoint.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-improve pipeline prompts against ground truth")
    parser.add_argument(
        "--agent",
        choices=_IMPROVABLE_AGENTS,
        default="triage",
        help="Which agent's prompt to improve",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Maximum number of improvement iterations",
    )
    args = parser.parse_args()
    run_loop(args.agent, args.iterations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
