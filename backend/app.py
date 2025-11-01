# app.py

import os
import sys
import platform
from pathlib import Path
from flask import Flask, request, jsonify
from flask_login import current_user
import logging

# Paths
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Extensions (DB + Login)
from extensions import db, login_manager
from models import User

# Blueprints
from auth.routes import auth_bp
from routes.ocr_routes import ocr_bp  # optional OCR JSON API

# NLP (existing)
from src.nlp.extract import get_nlp, extract_keyphrases, split_sentences
from src.nlp.relationships import build_cooccurrence_graph, extract_svo_edges
from src.nlp.hierarchy import build_hierarchy_tree

# OCR + Gemini structure
from services.ocr_pipeline import OCRConfig, extract_text_smart
from services.llm_post import llm_clean_and_structure
from services.structure_utils import filter_concepts, bullets_to_graph, relations_to_graph

import networkx as nx

# ✅ Configure Tesseract for Render/Linux
try:
    import pytesseract
    if platform.system() == 'Linux':
        # On Render, Tesseract is installed via Aptfile
        pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
        print("✅ Tesseract configured for Linux")
    elif os.environ.get('TESSERACT_CMD'):
        # Windows with env var
        pytesseract.pytesseract.tesseract_cmd = os.environ.get('TESSERACT_CMD')
        print(f"✅ Tesseract configured: {os.environ.get('TESSERACT_CMD')}")
except ImportError:
    print("⚠️ pytesseract not installed")

# Frontend static folder
CANDIDATES = [
    Path(__file__).resolve().parents[1] / "frontend",
    BASE_DIR / "frontend",
]

FRONTEND_DIR = next((p for p in CANDIDATES if p.exists()), BASE_DIR / "frontend")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="/")

# ✅ Configure logging for Render debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config ---
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# ✅ DB URI - Use persistent storage on Render
# Render provides DATABASE_URL for PostgreSQL, or use instance folder for SQLite
os.makedirs(app.instance_path, exist_ok=True)
db_path = os.path.join(app.instance_path, "notes.db")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Optional: require login to use /api/process
REQUIRE_LOGIN_FOR_OCR = os.environ.get("REQUIRE_LOGIN_FOR_OCR", "0") == "1"

# Init extensions
db.init_app(app)
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None

# Create tables on startup
with app.app_context():
    db.create_all()

# Load spaCy once
nlp = get_nlp()

# ---- helpers (fallback graph builders) ----
def nx_to_vis_tree(T: nx.DiGraph):
    nodes = [{"id": str(n), "label": str(n)} for n in T.nodes()]
    edges = []
    for u, v, d in T.edges(data=True):
        w = d.get("weight", 1)
        label = f"w={w}" if w and w > 1 else ""
        edges.append({"from": str(u), "to": str(v), "label": label})
    return nodes, edges

def edges_to_vis(edges):
    nodes = set()
    vis_edges = []
    for e in edges:
        s = str(e["source"])
        t = str(e["target"])
        nodes.add(s)
        nodes.add(t)
        vis_edges.append({"from": s, "to": t, "label": str(e.get("label", ""))})
    vis_nodes = [{"id": n, "label": n} for n in sorted(nodes)]
    return vis_nodes, vis_edges

# ---- Routes ----
@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.post("/api/process")
def process_notes():
    # Optional gate
    if REQUIRE_LOGIN_FOR_OCR and not current_user.is_authenticated:
        return jsonify({"error": "Login required"}), 401

    try:
        files = request.files.getlist("files")
        if not files:
            logger.warning("No files uploaded")
            return jsonify({"error": "No files uploaded"}), 400

        lang = request.form.get("lang", "en")
        try:
            top_k = int(request.form.get("top_k", "15"))
        except ValueError:
            top_k = 15

        ocr_engine = (request.form.get("ocr_engine", "gcv") or "gcv").lower()
        
        logger.info(f"Processing {len(files)} files with engine: {ocr_engine}, lang: {lang}")

        cfg = OCRConfig(
            engine=ocr_engine,
            lang=lang,
            dpi=400,
            deskew=True,
            denoise=True,
            binarize=True,
            morph=True,
            merge_columns=True,
            strip_headers_footers=True,
            drop_low_conf=0.0,
        )

        # OCR all uploads
        import tempfile
        extracted_texts, engines_used = [], []
        total_pages = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                path = Path(tmpdir) / (f.filename or "upload")
                f.save(str(path))
                
                logger.info(f"Processing file: {f.filename}")
                
                try:
                    res = extract_text_smart(str(path), cfg)
                except Exception as e:
                    logger.warning(f"OCR failed with {ocr_engine}: {str(e)}")
                    if ocr_engine == "gcv":
                        logger.info("Falling back to Tesseract")
                        cfg2 = OCRConfig(**{**cfg.__dict__, "engine": "tesseract"})
                        res = extract_text_smart(str(path), cfg2)
                    else:
                        raise

                extracted_texts.append(res["text"])
                engines_used.append(res["engine_used"])
                total_pages += int(res.get("pages", 0) or 0)

        raw_text = "\n\n".join(t for t in extracted_texts if t).strip()
        
        if not raw_text:
            logger.error("No text detected from OCR")
            return jsonify({"error": "No text detected. Try clearer scans or check Vision credentials."}), 200

        logger.info(f"Extracted {len(raw_text)} characters from {total_pages} pages")

        # ✅ Fixed: model_name parameter (was incorrectly placed)
        llm = llm_clean_and_structure(
            raw_text,
            summary_level=request.form.get("summary_level", "normal"),
            top_k_concepts=top_k,
            model_name="gemini-2.5-flash"  # Fixed: was request.form.get("gemini-1.5-flash")
        )

        cleaned_text = (llm.get("clean_text") or raw_text).strip()

        # Top concepts: Gemini-first with filtering
        llm_concepts = filter_concepts(llm.get("concepts"), top_k=top_k)
        if llm_concepts:
            keyphrases = [{"phrase": c, "score": float(f"{1.0 - i*0.01:.2f}")} for i, c in enumerate(llm_concepts)]
            kp_list = [k["phrase"] for k in keyphrases]
        else:
            sentences_tmp = split_sentences(cleaned_text, nlp)
            keyphrases_scored = extract_keyphrases(cleaned_text, nlp, top_k=top_k)
            keyphrases = [{"phrase": p, "score": s} for p, s in keyphrases_scored]
            kp_list = [kp for kp, _ in keyphrases_scored]

        # Mindmap: Gemini bullets -> tree (fallback to co-occurrence)
        mm = bullets_to_graph(llm.get("bullets") or [])
        if not mm["nodes"]:
            sentences = split_sentences(cleaned_text, nlp)
            G_cooc = build_cooccurrence_graph(sentences, kp_list)
            root = kp_list[0] if kp_list else None
            T_tree = build_hierarchy_tree(G_cooc, root=root)
            nodes, edges = nx_to_vis_tree(T_tree)
            mm = {"root": root, "nodes": nodes, "edges": edges}

        # Flowchart: Gemini relations -> graph (fallbacks)
        fc = relations_to_graph(llm.get("relations") or [])
        if not fc["nodes"]:
            fc = {"nodes": mm["nodes"], "edges": mm["edges"]}
        if not fc["nodes"]:
            sentences = split_sentences(cleaned_text, nlp)
            G = build_cooccurrence_graph(sentences, kp_list)
            svo_edges = extract_svo_edges(cleaned_text, kp_list, nlp)
            if not svo_edges:
                svo_edges = [{"source": u, "target": v, "label": f"w={d.get('weight',1)}"}
                             for u, v, d in G.edges(data=True)]
            nodes, edges = edges_to_vis(svo_edges)
            fc = {"nodes": nodes, "edges": edges}

        engine_used = list(dict.fromkeys(engines_used or ["none"]))[0]
        
        logger.info(f"Successfully processed request - Engine: {engine_used}, Concepts: {len(keyphrases)}")

        return jsonify({
            "text": cleaned_text,
            "keyphrases": keyphrases,
            "mindmap": mm,
            "flowchart": fc,
            "llm": llm,
            "meta": {
                "images_processed": total_pages,
                "ocr_engine": engine_used,
                "llm_provider": "gemini" if os.environ.get("GEMINI_API_KEY") else "fallback",
                "raw_excerpt": raw_text[:500],
                "user": current_user.username if current_user.is_authenticated else None
            }
        })

    except Exception as e:
        logger.error(f"Processing error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.get("/healthz")
def healthz():
    msgs = []
    if not os.environ.get("GEMINI_API_KEY"):
        msgs.append("GEMINI_API_KEY not set (LLM will fallback).")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        msgs.append("GOOGLE_APPLICATION_CREDENTIALS not set (Vision will fail; tesseract fallback).")
    return jsonify({"ok": True, "messages": msgs, "frontend": str(FRONTEND_DIR)})

# ✅ Register blueprints (THIS WAS MISSING!)
app.register_blueprint(auth_bp)
app.register_blueprint(ocr_bp)

if __name__ == "__main__":
    if os.environ.get("GEMINI_API_KEY"):
        print("✅ Gemini API ready")
    else:
        print("⚠️ GEMINI_API_KEY not set; deterministic fallback")
    
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("✅ Google Vision credentials detected")
    else:
        print("⚠️ GOOGLE_APPLICATION_CREDENTIALS not set; choose 'tesseract' or expect fallback")
    
    if os.name == "nt" and not os.environ.get("POPPLER_PATH"):
        print("ℹ️ Set POPPLER_PATH to your Poppler 'bin' folder (Windows)")
    
    print(f"DB: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"Require login for OCR: {REQUIRE_LOGIN_FOR_OCR}")
    app.run(host="127.0.0.1", port=5000, debug=True)
