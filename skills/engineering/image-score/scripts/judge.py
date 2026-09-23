#!/usr/bin/env python3
"""
Image Score — Structured image quality evaluation using LLM judges.

Usage:
    # Single image
    python judge.py --image cat.png --prompt "a cat in space"

    # Batch with JSONL input
    python judge.py --input images.jsonl --backend openai --model openai/gpt-4o

    # Gemini
    export GOOGLE_API_KEY="..."
    python judge.py --image cat.png --backend gemini --model gemini/gemini-2.5-pro
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from checklists import (
    DIM_TO_CHECKLIST,
    DIM_L2_NAMES,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from score_utils import (
    compute_dimension_score,
    aggregate_total,
    extract_json,
    format_terminal,
)
from backends import create_judge


# ── Image loading ─────────────────────────────────────────────────

def load_image(path: str) -> Image.Image:
    """Load and convert image to RGB."""
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


# ── Input loading ─────────────────────────────────────────────────

def load_input(path: str) -> list[dict]:
    """Load CSV, JSON, or JSONL input file."""
    ext = Path(path).suffix.lower()

    if ext == ".csv":
        import pandas as pd
        return pd.read_csv(path).to_dict(orient="records")

    with open(path, encoding="utf-8") as f:
        content = f.read().strip()

    if content.startswith("["):
        return json.loads(content)

    # JSONL: one JSON object per line
    return [json.loads(line) for line in content.splitlines() if line.strip()]


# ── Core logic ────────────────────────────────────────────────────

def score_image(judge, image_path: str, prompt: str = "",
                skip_alignment: bool = False) -> dict:
    """
    Score a single image across all applicable dimensions.

    Returns: {dim_name: {level1_score, level2_scores, details}, ...}
    """
    img = load_image(image_path)
    dims_to_score = [
        d for d in DIM_TO_CHECKLIST
        if not (d == "Alignment" and skip_alignment)
    ]
    tasks: list[dict] = []
    task_meta: list[str] = []

    for dim_name in dims_to_score:
        checklist = DIM_TO_CHECKLIST[dim_name]
        l2_names = DIM_L2_NAMES.get(dim_name, [])
        user_text = build_user_prompt(
            prompt or "(no prompt provided)",
            dim_name,
            checklist,
            l2_names,
        )

        tasks.append({
            "system_prompt": SYSTEM_PROMPT,
            "user_text": user_text,
            "image": img,
        })
        task_meta.append(dim_name)

    outputs = judge.generate_batch(tasks)

    results: dict[str, dict] = {}
    for dim_name, text in zip(task_meta, outputs):
        score_json = extract_json(text)
        if score_json is None:
            print(f"WARNING: Failed to parse JSON for {dim_name}. Raw output:")
            print(text[:500])
            results[dim_name] = {
                "level1_score": None,
                "level2_scores": {},
                "details": {},
                "_raw": text,
            }
            continue
        results[dim_name] = compute_dimension_score(score_json)
        results[dim_name]["_raw"] = text

    return results


# ── Main entry ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Score AI-generated images with an LLM judge"
    )
    # Input
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", help="Single image to score")
    group.add_argument("--input", help="Batch file (.csv/.json/.jsonl)")

    parser.add_argument("--prompt", default="",
                        help="Text prompt used to generate the image")
    parser.add_argument("--output", default="",
                        help="Output JSON file (default: auto-named)")

    # Judge
    parser.add_argument("--backend", default="openai",
                        choices=["openai", "gemini"],
                        help="Judge provider (default: openai)")
    parser.add_argument("--model", default="openai/gpt-4o",
                        help="Model name with provider prefix")
    parser.add_argument("--max-workers", type=int, default=8,
                        help="Concurrent API workers (default: 8)")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="Max output tokens (default: 4096)")

    args = parser.parse_args()

    # Create judge
    judge = create_judge(
        args.backend, args.model,
        max_workers=args.max_workers,
        max_tokens=args.max_tokens,
    )
    print(f"Judge: {args.model} via {args.backend}")

    # Run
    if args.image:
        skip_alignment = not args.prompt.strip()
        if skip_alignment:
            print("Note: No prompt provided — Alignment dimension skipped.")

        dims = score_image(judge, args.image, args.prompt, skip_alignment)
        total = aggregate_total(dims)

        result = {
            "meta": {
                "image": args.image,
                "prompt": args.prompt or None,
                "model": args.model,
                "backend": args.backend,
                "alignment_skipped": skip_alignment,
            },
            "dimensions": dims,
            "total": total,
        }

        # Terminal display
        print(format_terminal(result))

        # Save
        out_path = args.output or f"{Path(args.image).stem}_score.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved: {out_path}")

    elif args.input:
        rows = load_input(args.input)
        print(f"Loaded {len(rows)} entries from {args.input}")

        all_results = []
        for i, row in enumerate(rows):
            img_path = row.get("image_path", row.get("image", ""))
            prompt = row.get("prompt", args.prompt)
            if not img_path:
                print(f"Row {i}: no image path, skipping")
                continue

            print(f"\n[{i+1}/{len(rows)}] {img_path}")
            dims = score_image(judge, img_path, prompt,
                               skip_alignment=not prompt)
            total = aggregate_total(dims)
            all_results.append({
                "meta": {"image": img_path, "prompt": prompt},
                "dimensions": dims,
                "total": total,
            })

        # Batch summary
        scores = [r["total"] for r in all_results if r["total"] is not None]
        if scores:
            avg = sum(scores) / len(scores)
            print(f"\nBatch average: {avg:.0f} ({len(scores)} images)")

        out_path = args.output or f"{Path(args.input).stem}_scores.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
