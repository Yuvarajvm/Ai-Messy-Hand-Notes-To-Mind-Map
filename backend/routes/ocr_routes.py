# routes/ocr_routes.py
from __future__ import annotations
import os, tempfile
from flask import Blueprint, request, jsonify

from services.ocr_pipeline import OCRConfig, extract_text_smart, top_concepts
from services.llm_post import llm_clean_and_structure

ocr_bp = Blueprint("ocr_bp", __name__, url_prefix="/ocr")


def _to_bool(v, default=False):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower().strip() in {"1", "true", "yes", "on"}


@ocr_bp.route("/process", methods=["POST"])
def process_ocr():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "No files uploaded"}), 400

    cfg = OCRConfig(
        engine=request.form.get("engine", "gcv"),
        lang=request.form.get("lang", "en"),
        dpi=int(request.form.get("dpi", 400)),
        deskew=_to_bool(request.form.get("deskew", True), True),
        denoise=_to_bool(request.form.get("denoise", True), True),
        binarize=_to_bool(request.form.get("binarize", True), True),
        morph=_to_bool(request.form.get("morph", True), True),
        merge_columns=_to_bool(request.form.get("merge_columns", True), True),
        strip_headers_footers=_to_bool(request.form.get("strip_headers", True), True),
        drop_low_conf=float(request.form.get("drop_low_conf", 0.0)),
    )

    summary_level = request.form.get("summary_level", "normal")
    top_k = int(request.form.get("top_k_concepts", 12))
    gemini_model = request.form.get("gemini_model")

    texts, engines = [], []
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            path = os.path.join(tmpdir, f.filename or "upload")
            f.save(path)
            res = extract_text_smart(path, cfg)
            texts.append(res["text"])
            engines.append(res["engine_used"])

    extracted_text = "\n\n".join(t for t in texts if t).strip()
    llm_out = llm_clean_and_structure(
        extracted_text,
        summary_level=summary_level,
        top_k_concepts=top_k,
        model_name=gemini_model
    )

    concepts = top_concepts(llm_out.get("clean_text") or extracted_text, k=top_k)

    return jsonify({
        "ok": True,
        "engine_used": list(set(engines or ["none"]))[0],
        "extracted_text": extracted_text,
        "top_concepts": concepts,
        "llm": llm_out
    })