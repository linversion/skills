"""
Evaluation dimension definitions for image scoring.

A simplified 5×15 hierarchy distilled from Qwen-Image-Bench's 5×23×56.
Each checklist is a flat list of facets that the judge model evaluates.
"""

# ── Quality ──────────────────────────────────────────────────────

QUALITY_CHECKLIST = """## Clarity
- Is the overall image resolution high, free from visible pixelation,
  blur, or compression artifacts?
## AI Artifacts
- Does the image avoid unnatural "plastic" or "greasy" texture,
  over-smoothing, and other telltale signs of AI generation?
## Edge & Detail
- Are object edges sharp and well-defined? Is detail rich without
  excessive noise?"""

# ── Aesthetics ───────────────────────────────────────────────────

AESTHETICS_CHECKLIST = """## Composition
- Is the composition balanced with clear visual hierarchy and flow?
  Is the subject well-placed?
## Color Harmony
- Is the color palette cohesive and appropriate for the mood/scene?
  No clashing or washed-out tones.
## Lighting
- Are light sources consistent? Do shadows fall naturally? Does the
  lighting atmosphere match the scene?
## Style Control
- If the prompt specifies an artistic style (e.g. cyberpunk, oil
  painting, manga), does the image faithfully reproduce it?"""

# ── Alignment (prompt faithfulness) ──────────────────────────────

ALIGNMENT_CHECKLIST = """## Object Accuracy
- Do the count, color, shape, and material of objects match the prompt?
## Spatial Relations
- Are positions (left/right, front/back, above/below), occlusion,
  and spatial logic consistent with the prompt?
## Action & Pose
- Do the actions, poses, facial expressions, and interactions of
  characters match what the prompt describes?
## Scene Match
- Does the environment (office, forest, street, space, etc.) match
  the prompt? Are scene elements faithful?"""

# ── Real-world Fidelity ──────────────────────────────────────────

REAL_WORLD_CHECKLIST = """## Physical Logic
- Do gravity, reflections, shadow direction, object stability, and
  other physical laws hold? Any obvious violations?
## World Knowledge
- Are real-world animals, objects, landmarks, and brand logos
  rendered accurately? No hallucinated or distorted details?
## Safety & Culture
- Is the image free from harmful stereotypes, cultural
  misrepresentations, NSFW content, and hate symbols?"""

# ── Creative Generation ──────────────────────────────────────────

CREATIVE_CHECKLIST = """## Text Rendering
- If the image contains text, is it legible, correctly spelled, and
  well-laid-out? No garbled characters or typos.
## Design Sense
- Does the image demonstrate design thinking (information hierarchy
  for posters, ergonomic logic for products, spatial proportion for
  architecture)?
## Narrative Expression
- Does the image tell a story? Is there emotional resonance, visual
  storytelling, cinematic framing, or directorial intent?"""

# ── Dimension registry ───────────────────────────────────────────

DIM_TO_CHECKLIST = {
    "Quality": QUALITY_CHECKLIST,
    "Aesthetics": AESTHETICS_CHECKLIST,
    "Alignment": ALIGNMENT_CHECKLIST,
    "Real-world Fidelity": REAL_WORLD_CHECKLIST,
    "Creative Generation": CREATIVE_CHECKLIST,
}

# ── Prompts for the judge model ──────────────────────────────────

SYSTEM_PROMPT = (
    "You are an expert evaluator for AI-generated image quality. "
    "You evaluate images on specific, well-defined criteria using a "
    "structured checklist. Be rigorous and objective. Avoid vague "
    "praise. Your job is to help identify concrete strengths and "
    "weaknesses so the creator can improve their generation pipeline."
)


USER_PROMPT_TEMPLATE = """\
# Generation Prompt
{prompt}

# Generated Image
<image>

# Evaluation Dimension
{level1_dim}

# Scoring Rules
- **0 (Fail)**: Clear defect present. Would noticeably hurt image quality.
- **1 (Pass)**: No defect. Meets baseline expectations.
- **2 (Excel)**: Exceptionally well executed. Concrete excellence is visible.
- **N/A**: This criterion does not apply to this image/prompt combination.

# Checklist
{format_checklist}

# Output Format
Return ONLY a valid JSON object (no markdown fences, no extra text):

{format_json}

The "rationale" field must be a single sentence. Do not write essays."""


def build_user_prompt(prompt_text: str, level1_dim: str,
                      checklist: str, l2_names: list[str]) -> str:
    """
    Build a complete user prompt with the correct JSON field names
    already filled in to reduce parse errors.
    """
    fields = ",\n".join(
        f'    "{name}": {{"score": 0, "rationale": ""}}'
        for name in l2_names
    )
    format_json = "{\n" + fields + "\n}"
    return USER_PROMPT_TEMPLATE.format(
        prompt=prompt_text,
        level1_dim=level1_dim,
        format_checklist=checklist,
        format_json=format_json,
    )

USER_PROMPT_TEMPLATE = f"""{USER_PROMPT_TEMPLATE}"""

# Map L1 → list of L2 names (for output format hints)
DIM_L2_NAMES = {
    "Quality": ["Clarity", "AI Artifacts", "Edge & Detail"],
    "Aesthetics": ["Composition", "Color Harmony", "Lighting", "Style Control"],
    "Alignment": ["Object Accuracy", "Spatial Relations", "Action & Pose", "Scene Match"],
    "Real-world Fidelity": ["Physical Logic", "World Knowledge", "Safety & Culture"],
    "Creative Generation": ["Text Rendering", "Design Sense", "Narrative Expression"],
}
