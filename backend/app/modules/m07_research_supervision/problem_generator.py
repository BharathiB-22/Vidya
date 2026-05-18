"""
M07 Problem Generator — LLM-based research problem generation for guides.

Given a guide's research area description, generates 3–5 candidate research
problems, each with: title, abstract (3–5 sentences), 3 research questions,
and a brief reasoning for why this is a timely/impactful problem.

Uses Gemini Flash (primary) → Groq fallback — same pattern as M03/M06.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import re

from app.config import settings

logger = logging.getLogger("vidya.m07.problem_generator")


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class GeneratedProblem:
    title:              str
    abstract:           str
    research_questions: list[str]
    reasoning:          str


@dataclasses.dataclass
class ProblemGenerationResult:
    problems:  list[GeneratedProblem]
    ai_model:  str
    prompt_hash: str


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _build_prompt(research_area: str, num_problems: int) -> str:
    return f"""You are an academic research advisor helping a faculty member identify high-impact research problems.

Research area: {research_area}

Generate exactly {num_problems} research problem proposals. For each problem:
1. Write a clear, specific title (under 20 words).
2. Write a 3–5 sentence abstract explaining the problem, its significance, and the proposed approach.
3. List exactly 3 specific, answerable research questions.
4. Write one sentence of reasoning explaining why this problem is timely and impactful.

Respond ONLY with a JSON array. Each element must have these exact keys:
  "title", "abstract", "research_questions" (array of 3 strings), "reasoning"

Example structure:
[
  {{
    "title": "...",
    "abstract": "...",
    "research_questions": ["...", "...", "..."],
    "reasoning": "..."
  }}
]

Generate {num_problems} problems now:"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_problems(raw: str, expected: int) -> list[GeneratedProblem]:
    # Strip markdown fences if present
    raw = re.sub(r"```json\s*|\s*```", "", raw).strip()

    # Attempt JSON parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract first JSON array
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            raise ValueError(f"LLM did not return a JSON array. Raw: {raw[:200]}")
        data = json.loads(m.group(0))

    if not isinstance(data, list):
        raise ValueError("Expected JSON array of problems.")

    problems: list[GeneratedProblem] = []
    for item in data[:expected]:
        rqs = item.get("research_questions", [])
        if isinstance(rqs, list):
            rqs = [str(q) for q in rqs[:3]]
        else:
            rqs = [str(rqs)]
        problems.append(GeneratedProblem(
            title=str(item.get("title", "")).strip(),
            abstract=str(item.get("abstract", "")).strip(),
            research_questions=rqs,
            reasoning=str(item.get("reasoning", "")).strip(),
        ))
    return problems


# ---------------------------------------------------------------------------
# LLM call (Gemini → Groq fallback)
# ---------------------------------------------------------------------------

async def _call_gemini(prompt: str) -> tuple[str, str]:
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    response = model.generate_content(prompt)
    return response.text, settings.GEMINI_MODEL


async def _call_groq(prompt: str) -> tuple[str, str]:
    import httpx
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return text, settings.GROQ_MODEL


async def _call_llm(prompt: str) -> tuple[str, str]:
    provider = settings.AI_PROVIDER
    if provider == "groq":
        return await _call_groq(prompt)
    if provider == "gemini":
        return await _call_gemini(prompt)
    # fallback: try gemini, then groq
    try:
        return await _call_gemini(prompt)
    except Exception as gemini_err:
        logger.warning("Gemini failed, trying Groq: %s", gemini_err)
        return await _call_groq(prompt)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_problems(
    research_area: str,
    *,
    num_problems: int = 3,
) -> ProblemGenerationResult:
    prompt = _build_prompt(research_area, num_problems)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

    raw_text, model_name = await _call_llm(prompt)
    problems = _parse_problems(raw_text, num_problems)

    logger.info(
        "Generated %d research problems for area=%r model=%s",
        len(problems), research_area[:40], model_name
    )
    return ProblemGenerationResult(
        problems=problems,
        ai_model=model_name,
        prompt_hash=prompt_hash,
    )
