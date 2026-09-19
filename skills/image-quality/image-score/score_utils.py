"""
Score extraction, mapping, and aggregation.

Follows Qwen-Image-Bench methodology:
  L3 raw (0/1/2/NA) → map (0→0, 1→60, 2→100, NA→skip)
  → L2 = mean(valid L3s) → L1 = mean(valid L2s) → Total = mean(valid L1s)
"""

import json
import re
from collections import defaultdict
from typing import Any

SCORE_MAP: dict = {0: 0.0, 1: 60.0, 2: 100.0}


def extract_json(text: str) -> dict | None:
    """
    Extract JSON from model output.

    Handles:
    - Pure JSON
    - JSON inside markdown fences (```json ... ```)
    - JSON after text/garbage
    - Output with thinking/reasoning prefix
    """
    if not text:
        return None

    # Strip thinking tags if present
    think_end = text.rfind("<｜end▁of▁thinking｜>")
    if think_end == -1:
        think_end = text.rfind("\n\n")
    if think_end != -1:
        # Try the portion after think/first double-newline
        pass  # fall through to full-text attempt

    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # Find first { ... } block
    brace = re.search(r'\{[\s\S]*\}', text)
    if brace:
        try:
            return json.loads(brace.group())
        except json.JSONDecodeError:
            pass

    return None


def map_score(raw: Any) -> float | None:
    """Map raw score: 0→0, 1→60, 2→100, 'N/A'→None."""
    if isinstance(raw, str) and raw.strip().upper() == "N/A":
        return None
    try:
        return SCORE_MAP[int(raw)]
    except (KeyError, ValueError, TypeError):
        return None


def _mean(values: list[float]) -> float | None:
    """Mean of non-None values. Returns None if empty."""
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def compute_dimension_score(score_json: dict) -> dict:
    """
    Compute aggregated score for one L1 dimension.

    Input:
      {"Clarity": {"score": 1, "rationale": "..."}, ...}
    Output:
      {
        "level1_score": 70.0,
        "level2_scores": {"Clarity": 60.0, "AI Artifacts": 80.0},
        "details": {"Clarity": {"score": 60, "rationale": "..."}, ...}
      }
    """
    level2_scores: dict[str, float | None] = {}
    details: dict[str, dict] = {}

    for l2_name, entry in score_json.items():
        raw_score = entry.get("score") if isinstance(entry, dict) else entry
        mapped = map_score(raw_score)
        level2_scores[l2_name] = mapped
        details[l2_name] = {
            "score": mapped,
            "rationale": entry.get("rationale", "") if isinstance(entry, dict)
                         else "",
        }

    level1 = _mean([s for s in level2_scores.values() if s is not None])
    return {
        "level1_score": level1,
        "level2_scores": level2_scores,
        "details": details,
    }


def aggregate_total(dim_results: dict[str, dict]) -> float | None:
    """
    Aggregate across all L1 dimensions to a total score.

    Input: {"Quality": {"level1_score": 60.0, ...}, ...}
    """
    scores = [
        r["level1_score"]
        for r in dim_results.values()
        if r.get("level1_score") is not None
    ]
    return _mean(scores)


def format_bar(score: float | None, width: int = 10) -> str:
    """Render a simple ASCII bar: ████░░░░░░ 60"""
    if score is None:
        return "─" * width + " N/A"
    filled = int(round(score / 100 * width))
    return "█" * filled + "░" * (width - filled) + f" {score:.0f}"


def format_terminal(result: dict) -> str:
    """
    Format scoring result for terminal display.

    Input: the full result dict from judge.py
    Returns: a pretty string for terminal output.
    """
    lines = ["", "📊 Image Score", "=" * 40]

    dims = result.get("dimensions", {})
    for dim_name in ["Quality", "Aesthetics", "Alignment",
                      "Real-world Fidelity", "Creative Generation"]:
        dim = dims.get(dim_name)
        if dim is None:
            lines.append(f"{dim_name:<16} {'─'*10} (skipped)")
            continue
        score = dim.get("level1_score")
        bar = format_bar(score)
        lines.append(f"{dim_name:<16} {bar}")

        # Sub-items on one line
        subs = []
        for l2_name, info in dim.get("details", {}).items():
            s = info.get("score")
            if s is not None:
                subs.append(f"{l2_name}={s:.0f}")
            else:
                subs.append(f"{l2_name}=N/A")
        if subs:
            lines.append(f"  {'← ' + ' | '.join(subs)}")

    total = result.get("total")
    lines.append("-" * 40)
    lines.append(f"{'Overall':<16} {format_bar(total)}")

    # Highlights
    highlights = _find_highlights(result)
    if highlights.get("best"):
        lines.append(f"\n✨ Best: {', '.join(highlights['best'])}")
    if highlights.get("worst"):
        lines.append(f"⚠  Needs work: {', '.join(highlights['worst'])}")

    return "\n".join(lines)


def _find_highlights(result: dict) -> dict[str, list[str]]:
    """Find best (100) and worst (0) scoring items."""
    best: list[str] = []
    worst: list[str] = []
    for dim in result.get("dimensions", {}).values():
        for name, info in dim.get("details", {}).items():
            s = info.get("score")
            if s == 100:
                best.append(name)
            elif s == 0:
                worst.append(f"{name}(0)")
    return {"best": best, "worst": worst}
