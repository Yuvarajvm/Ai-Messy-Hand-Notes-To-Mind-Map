# services/llm_post.py
from __future__ import annotations
import os, json
from typing import Dict, Any, List

from services.ocr_pipeline import cleanup_text, top_concepts

def llm_clean_and_structure(raw_text: str,
                            summary_level: str = "normal",
                            top_k_concepts: int = 12,
                            model_name: str = None) -> Dict[str, Any]:
    """
    Returns dict:
      clean_text, bullets (list of {t, children}), concepts (list[str]), relations (list[[a,b]])
    """
    text = cleanup_text(raw_text)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _fallback(text, top_k_concepts)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"))

        prompt = _prompt(summary_level, top_k_concepts)
        # Use dict for wide compatibility of SDK versions
        resp = model.generate_content(
            [prompt, "\n\n----\n", text],
            generation_config={
                "temperature": 0.2,
                "top_p": 0.95,
                "response_mime_type": "application/json",
            },
        )
        content = resp.text or ""
        data = _safe_json(content) or _extract_json_from_text(content)
        return _with_defaults(data, text, top_k_concepts)
    except Exception:
        return _fallback(text, top_k_concepts)


def _prompt(summary_level: str, top_k_concepts: int) -> str:
    return f"""
You will receive noisy OCR text. Clean it and return a structured JSON.

Tasks:
1) Fix casing, punctuation, spacing. Remove duplicate lines and page headers/footers.
2) Keep technical terms as-is. Do not invent facts.
3) Build hierarchical bullets (max depth 3) capturing key ideas.
4) Extract the top {top_k_concepts} keyphrases (short noun phrases; no stopwords).
5) Provide simple parent→child relations inferred from the bullets.

Output JSON schema:
{{
  "clean_text": "string",
  "bullets": [{{"t": "string", "children": [{{"t": "string","children":[...]}}]}}],
  "concepts": ["string", "..."],
  "relations": [["Parent","Child"], ["Topic","Subtopic"]]
}}

Summarization level: {summary_level}.
Return ONLY valid JSON (no markdown).
    """.strip()


def _safe_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_json_from_text(s: str):
    import re, json
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _heuristic_bullets(text: str):
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    bullets: List[dict] = []
    for p in paras[:25]:
        line = p.split("\n")[0]
        if len(line) <= 120:
            bullets.append({"t": line, "children": []})
    return bullets


def _with_defaults(data: Dict[str, Any] | None, text: str, top_k: int):
    if not data:
        return _fallback(text, top_k)
    data.setdefault("clean_text", text)
    data.setdefault("bullets", _heuristic_bullets(text))
    data.setdefault("concepts", top_concepts(text, k=top_k))
    data.setdefault("relations", [])
    return data


def _fallback(text: str, top_k: int):
    return {
        "clean_text": text,
        "bullets": _heuristic_bullets(text),
        "concepts": top_concepts(text, k=top_k),
        "relations": []
    }