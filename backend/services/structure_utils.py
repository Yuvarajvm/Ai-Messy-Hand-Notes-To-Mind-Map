# services/structure_utils.py
from __future__ import annotations
from typing import List, Dict, Any

def titleize(s: str) -> str:
    s = " ".join(s.split())
    if not s:
        return s
    return s if s.isupper() else s.title()

def normalize_key(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

GENERIC_TERMS = {
    "data", "information", "system", "model", "process", "method",
    "approach", "technique", "paper", "study", "result"
}
HARD_STOP = {
    "this", "that", "these", "those", "here", "there",
    "allow", "allows", "allowing", "allowed",
    "input", "tier", "task", "primitives", "things", "stuff"
}

def filter_concepts(concepts: List[str] | None, top_k: int = 12) -> List[str]:
    seen = set()
    cleaned = []
    for c in concepts or []:
        if not isinstance(c, str):
            continue
        key = normalize_key(c)
        if not key or len(key) < 3:
            continue
        if key in HARD_STOP:
            continue
        if " " not in key and key in GENERIC_TERMS:
            continue
        if key not in seen:
            seen.add(key)
            cleaned.append(titleize(c))
        if len(cleaned) >= top_k:
            break
    return cleaned

def bullets_to_graph(bullets: List[Dict[str, Any]]):
    """
    bullets: [{"t":"Node","children":[...]}]
    Returns: {"root": label, "nodes":[{id,label}], "edges":[{from,to,label}]}
    """
    if not bullets:
        return {"root": None, "nodes": [], "edges": []}

    id_map = {}
    def get_id(label: str):
        label = titleize(label or "")
        key = normalize_key(label)
        if key and key not in id_map:
            id_map[key] = label
        return key

    edges = []
    roots = []

    def walk(node, parent_key=None, depth=0):
        label = node.get("t") if isinstance(node, dict) else None
        if not isinstance(label, str) or not label.strip():
            return
        key = get_id(label)
        if not key:
            return
        if depth == 0:
            roots.append(key)
        if parent_key and key != parent_key:
            edges.append((parent_key, key))
        for child in (node.get("children") or []):
            walk(child, key, depth+1)

    for top in bullets:
        walk(top, None, 0)

    nodes = [{"id": k, "label": id_map[k]} for k in id_map.keys()]
    from collections import Counter
    cnt = Counter(edges)
    vis_edges = [{"from": a, "to": b, "label": f"w={w}"} for (a, b), w in cnt.items()]
    root = roots[0] if roots else (nodes[0]["id"] if nodes else None)
    return {"root": id_map.get(root, root), "nodes": nodes, "edges": vis_edges}

def relations_to_graph(relations: List[List[str]] | None):
    """
    relations: [["Parent","Child"], ...]
    Returns: {"nodes":[{id,label}], "edges":[{from,to,label}]}
    """
    if not relations:
        return {"nodes": [], "edges": []}
    id_map = {}
    def get_id(label: str):
        label = titleize(label or "")
        key = normalize_key(label)
        if key and key not in id_map:
            id_map[key] = label
        return key
    edges = []
    for pair in relations:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        a, b = pair[0], pair[1]
        if not isinstance(a, str) or not isinstance(b, str):
            continue
        ak = get_id(a); bk = get_id(b)
        if ak and bk and ak != bk:
            edges.append((ak, bk))
    from collections import Counter
    cnt = Counter(edges)
    nodes = [{"id": k, "label": v} for k, v in id_map.items()]
    vis_edges = [{"from": a, "to": b, "label": f"w={w}"} for (a, b), w in cnt.items()]
    return {"nodes": nodes, "edges": vis_edges}