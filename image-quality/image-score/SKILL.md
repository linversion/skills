---
name: image-score
description: >
  Score AI-generated images with an LLM judge across 5 dimensions
  (Quality, Aesthetics, Alignment, Real-world Fidelity, Creative
  Generation). Use when the user asks to rate, evaluate, score, or
  review an AI-generated image, compare model outputs, check if a
  prompt change improved generation quality, or get structured
  feedback on image generation results. Also trigger for requests
  like "how good is this image", "evaluate my generation", "judge
  this output", "compare these two images", "did my prompt change
  help", or any time they want an objective, multi-dimensional
  assessment of image quality.
compatibility: openai, google-genai, Pillow
---

# Image Score

Structured AI image evaluation. Give the model an image (and
optionally the prompt that generated it), and it returns a
five-dimension scorecard with specific strengths and weaknesses.

## When to Use

- User wants to rate/evaluate/score an AI-generated image
- User wants to compare two generation outputs
- User asks "is this image good" or "how can I improve this"
- User changed a prompt and wants to know if the result actually got better
- User is iterating on a T2I pipeline and needs structured feedback

**Skip this skill if:**
- The image is a photograph, not AI-generated (the framework expects
  AI generation artifacts)
- The user just wants a casual opinion ("does this look cool?")
- The user is asking about image metadata, format conversion, etc.

## Quick Start

```bash
# Score a single image (no prompt → Alignment skipped)
python scripts/judge.py --image output.png

# Score with prompt (all 5 dimensions)
python scripts/judge.py --image output.png \
  --prompt "a cat wearing a spacesuit on Mars, cinematic lighting"

# Use Gemini
export GOOGLE_API_KEY="..."
python scripts/judge.py --image output.png \
  --backend gemini --model gemini/gemini-2.5-pro

# Batch scoring from a JSONL file
python scripts/judge.py --input images.jsonl \
  --backend openai --model openai/gpt-4o
```

## Evaluation Framework

Five dimensions, 17 sub-items. Each sub-item scored 0/1/2/N/A,
mapped to 0/60/100, then averaged bottom-up.

| Dimension | What It Checks |
|-----------|---------------|
| **Quality** | Clarity, AI artifacts, edge detail |
| **Aesthetics** | Composition, color, lighting, style control |
| **Alignment** | Object accuracy, spatial relations, actions, scene match |
| **Real-world Fidelity** | Physical logic, world knowledge, safety & culture |
| **Creative Generation** | Text rendering, design sense, narrative expression |

**Alignment is skipped when no prompt is provided** — you can't check
prompt faithfulness without a prompt.

Each sub-item also gets a one-sentence `rationale` explaining the
score, so the user knows *why* not just *what*.

## Backend Abstraction

Two backends, same interface. The judge script auto-creates the right
one from `--backend`.

### OpenAI (`openai`)

Any OpenAI-compatible endpoint. Set `OPENAI_BASE_URL` for vLLM,
Ollama, Groq, DeepSeek, etc.

```bash
export OPENAI_API_KEY="sk-..."
# optional custom endpoint:
export OPENAI_BASE_URL="http://localhost:8000/v1"
python scripts/judge.py --backend openai --model openai/gpt-4o --image out.png
```

### Gemini (`gemini`)

Uses `google-genai` SDK.

```bash
export GOOGLE_API_KEY="..."
python scripts/judge.py --backend gemini --model gemini/gemini-2.5-pro --image out.png
```

### Adding a New Backend

1. Create `backends/your_backend.py` inheriting from `BaseJudgeBackend`
2. Implement `_build_payload(item)` and `_call(payload)`
3. Register in `backends/__init__.py` → `BACKENDS` dict

## Output

### Terminal

A compact summary with ASCII bars and highlights:

```
📊 Image Score
========================================
Quality           ████████░░ 80
  ← Clarity=100 | AI Artifacts=60 | Edge & Detail=80
Aesthetics        █████████░ 87
  ← Composition=100 | Color=80 | Lighting=80 | Style Control=80
...

✨ Best: Clarity, Composition
⚠  Needs work: Text Rendering(0)
```

### JSON File

Full structured output saved as `{image}_score.json`:

```json
{
  "meta": {
    "image": "output.png",
    "prompt": "a cat in space",
    "model": "openai/gpt-4o",
    "backend": "openai"
  },
  "dimensions": {
    "Quality": {
      "level1_score": 80.0,
      "level2_scores": {"Clarity": 100.0, "AI Artifacts": 60.0},
      "details": {
        "Clarity": {"score": 100.0, "rationale": "Image is sharp..."},
        "AI Artifacts": {"score": 60.0, "rationale": "Slight plastic texture"}
      }
    }
  },
  "total": 78.0
}
```

JSON output is designed to be `git diff` friendly — run before/after
a prompt change and diff the files to see exactly what improved.

## Limitations

- **Judge bias**: GPT-4o and Gemini are general-purpose MLLMs, not
  calibrated image evaluators. Scores are a structured reference,
  not objective ground truth. Different models may score differently.
- **No human baseline**: Unlike Qwen-Image-Bench (Spearman ρ=0.92 with
  80 professional annotators), this skill uses off-the-shelf models
  with no calibration. Use for relative comparison, not absolute claims.
- **Cost**: Each image does 4-5 API calls. At ~$0.01/call with GPT-4o,
  expect ~$0.05/image. Batch mode compounds this.
- **Not an art critic**: The framework tests technical and semantic
  quality, not artistic merit. "Is this good art" is a different
  question from "is this a well-executed generation."

## Single Image Workflow

When a user asks to score a single image:

1. Confirm the image path and check if a prompt is available
2. Run `python scripts/judge.py --image <path> [--prompt "..."]`
3. Read the result and highlight the key findings
4. If the total score is low on a specific dimension, suggest what
   might be causing it based on the rationales

## Batch Workflow

When comparing multiple images or models:

1. Prepare a JSONL file with `image_path` and optional `prompt` fields
2. Run `python scripts/judge.py --input <file>`
3. Parse the output JSON for comparative analysis
4. Show which images scored highest/lowest per dimension

## Comparison Workflow

When asked to compare two images:

1. Score both independently: `scripts/judge.py --image a.png` and
   `scripts/judge.py --image b.png`
2. Parse both JSON outputs
3. Present a side-by-side comparison focusing on:
   - Overall score difference
   - Per-dimension delta (which image wins on what)
   - Specific items with the largest score gaps
4. Summarize: which image is better, and *on what dimensions*
