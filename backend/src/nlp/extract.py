import re
from collections import Counter
from typing import List, Tuple
import spacy

def get_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        # Fallback: blank English with sentencizer only (reduced features)
        nlp = spacy.blank("en")
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        return nlp

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def split_sentences(text: str, nlp) -> List[str]:
    doc = nlp(text)
    return [normalize_space(s.text) for s in doc.sents if s.text.strip()]

def _noun_chunks_or_tokens(doc):
    chunks = []
    # Try noun chunks if parser present
    if hasattr(doc, "noun_chunks"):
        try:
            for ch in doc.noun_chunks:
                chunks.append(ch.text)
        except Exception:
            pass
    if not chunks:
        tokens = []
        for t in doc:
            if getattr(t, "pos_", "") in ("NOUN", "PROPN") and len(t.text) > 2:
                tokens.append(t.text)
        if tokens:
            chunks = tokens
    return chunks

def extract_keyphrases(text: str, nlp, top_k: int = 15) -> List[Tuple[str, float]]:
    cleaned = re.sub(r"[^A-Za-z0-9\s\-\:_/]", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned)
    doc = nlp(cleaned)

    candidates = _noun_chunks_or_tokens(doc)
    if not candidates:
        candidates = re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", text)

    def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    cand_norm = [norm(c) for c in candidates if len(c.strip()) > 1]
    freq = Counter(cand_norm)

    # Boost early-title candidates
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    early = " ".join(lines[:3]).lower() if lines else ""
    boosts = Counter({c: 2 for c in cand_norm if c in early})

    scores = {c: freq[c] + boosts[c] + min(len(c.split()), 3) * 0.2 for c in freq}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Deduplicate: keep longest unique variants
    dedup = []
    seen = set()
    for phrase, sc in ranked:
        if phrase in seen: 
            continue
        if any(phrase in p for p, _ in dedup):
            continue
        dedup.append((phrase, sc))
        seen.add(phrase)
        if len(dedup) >= top_k:
            break

    # Map normalized back to original
    orig_map = {}
    for c in candidates:
        n = norm(c)
        if n in dict(dedup) and (n not in orig_map or len(c) > len(orig_map[n])):
            orig_map[n] = c.strip()

    out = [(orig_map.get(p, p), float(sc)) for p, sc in dedup]
    return out