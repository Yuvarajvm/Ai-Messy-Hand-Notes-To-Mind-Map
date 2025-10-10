from typing import List, Dict
import itertools
import re
import networkx as nx

def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def build_cooccurrence_graph(sentences: List[str], keyphrases: List[str]) -> nx.Graph:
    kp_norm = {_normalize(k): k for k in keyphrases}
    G = nx.Graph()
    for k in keyphrases:
        G.add_node(k)
    for sent in sentences:
        s = _normalize(sent)
        present = [kp_norm[nk] for nk in kp_norm if nk and nk in s]
        present = list(dict.fromkeys(present))
        if len(present) > 1:
            for u, v in itertools.combinations(present, 2):
                if G.has_edge(u, v):
                    G[u][v]["weight"] += 1
                else:
                    G.add_edge(u, v, weight=1)
    return G

def extract_svo_edges(text: str, keyphrases: List[str], nlp) -> List[Dict]:
    doc = nlp(text)
    edges = []
    kp_norm = {_normalize(k): k for k in keyphrases}

    def match_kp(fragment: str):
        fs = _normalize(fragment)
        matches = [kp_norm[nk] for nk in kp_norm if nk in fs]
        if not matches:
            return None
        matches.sort(key=len, reverse=True)
        return matches[0]

    # Requires POS/deps (works best with en_core_web_sm)
    for sent in getattr(doc, "sents", [doc]):
        sdoc = nlp(sent.text) if hasattr(nlp, "pipe_names") and "parser" in nlp.pipe_names else doc
        for token in sdoc:
            if getattr(token, "pos_", "") == "VERB":
                subj = None
                obj = None
                for child in token.children:
                    if child.dep_ in ("nsubj", "nsubjpass") and subj is None:
                        subj = child.subtree
                    if child.dep_ in ("dobj", "attr", "pobj", "dative") and obj is None:
                        obj = child.subtree
                if subj and obj:
                    s_text = " ".join([t.text for t in subj])
                    o_text = " ".join([t.text for t in obj])
                    s_kp = match_kp(s_text)
                    o_kp = match_kp(o_text)
                    if s_kp and o_kp and s_kp != o_kp:
                        edges.append({
                            "source": s_kp, "target": o_kp,
                            "label": getattr(token, "lemma_", token.text), "weight": 1
                        })

    # Merge duplicates
    merged = {}
    for e in edges:
        key = (e["source"], e["target"], e.get("label",""))
        merged[key] = merged.get(key, 0) + e.get("weight", 1)
    out = [{"source": s, "target": t, "label": l, "weight": w} for (s, t, l), w in merged.items()]
    return out