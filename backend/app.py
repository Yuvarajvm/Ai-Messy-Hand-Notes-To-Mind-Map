# app.py
import os
import sys
import tempfile
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_login import current_user, login_required
import networkx as nx
from services.pdf_export import export_results_to_pdf

# ========== PATHS ==========
BASE_DIR = Path(__file__).resolve().parent.parent  # Project root
FRONTEND_DIR = BASE_DIR / "frontend"
BACKEND_DIR = BASE_DIR / "backend"
SRC_DIR = BACKEND_DIR / "src"

# Add src to path for imports
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ========== EXTENSIONS & MODELS ==========
from extensions import db, login_manager
from models import User

# ========== BLUEPRINTS ==========
from auth.routes import auth_bp

# ========== NLP MODULES ==========
from src.nlp.extract import get_nlp, extract_keyphrases
from src.nlp.relationships import build_cooccurrence_graph, extract_svo_edges
from src.nlp.hierarchy import build_hierarchy_tree

# ========== OCR & SERVICES ==========
from services.ocr_pipeline import OCRConfig, extract_text_smart
from services.llm_post import llm_clean_and_structure, extract_mindmap_with_gemini
from services.structure_utils import filter_concepts, bullets_to_graph, relations_to_graph

# ========== LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

# ========== CREATE FLASK APP ==========
def create_app():
    """Create and configure Flask application"""
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path=''
    )
    
    # ===== CONFIGURATION =====
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Database setup
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        instance_dir = BASE_DIR / "instance"
        instance_dir.mkdir(exist_ok=True)
        db_path = instance_dir / "notes.db"
        db_url = f"sqlite:///{db_path}"
        logger.info(f"DB: {db_url}")
    
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Upload settings
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB max
    app.config["JSON_AS_ASCII"] = False
    
    # ===== INITIALIZE EXTENSIONS =====
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    
    # Create database tables
    with app.app_context():
        db.create_all()
        logger.info("Database tables created")
    
    return app

app = create_app()

# ========== CORS HEADERS ==========
@app.after_request
def after_request(response):
    """Add CORS headers to all responses"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ========== USER LOADER ==========
@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    return db.session.get(User, int(user_id))

# ========== FRONTEND ROUTES ==========
@app.route("/")
def index():
    """Serve main index page"""
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    """Serve static files from frontend folder"""
    try:
        return send_from_directory(FRONTEND_DIR, filename)
    except Exception as e:
        logger.error(f"File not found: {filename}")
        return jsonify({"error": "File not found"}), 404

# ========== REGISTER BLUEPRINTS ==========
app.register_blueprint(auth_bp)

# ========== MAIN PROCESSING API ==========
@app.route("/api/process", methods=["POST"])
def api_process():
    """
    Main API endpoint for processing uploaded notes
    Uses Google Vision OCR + Gemini AI for intelligent processing
    """
    try:
        files = request.files.getlist("files")
        if not files or len(files) == 0:
            return jsonify({"error": "No files uploaded"}), 400

        ocr_engine = request.form.get("ocr_engine", "gcv")
        lang = request.form.get("lang", "en")
        top_k = int(request.form.get("top_k", 12))
        summary_level = request.form.get("summary_level", "normal")

        logger.info(f"Processing {len(files)} files with engine: {ocr_engine}, lang: {lang}")

        all_text: list[str] = []
        file_results: list[dict] = []

        # ========== STEP 1: OCR EXTRACTION ==========
        for file in files:
            if not file or not file.filename:
                continue

            filename = file.filename
            logger.info(f"Processing file: {filename}")

            suffix = Path(filename).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                file.save(tmp.name)
                temp_path = tmp.name

            try:
                cfg = OCRConfig(
                    engine=ocr_engine,
                    lang=lang,
                    dpi=400,
                    deskew=True,
                    denoise=True,
                    binarize=True,
                    morph=True,
                )

                raw_text = extract_text_smart(temp_path, cfg)

                if isinstance(raw_text, dict):
                    logger.warning("extract_text_smart returned dict; using 'text' field")
                    raw_text = str(raw_text.get("text", ""))

                if not raw_text or len(raw_text.strip()) < 10:
                    logger.warning(f"No text extracted from {filename}")
                    file_results.append({
                        "filename": filename,
                        "status": "no_text",
                        "text_length": 0,
                    })
                    continue

                logger.info(f"✅ Extracted {len(raw_text)} characters from {filename}")

                if len(raw_text) > 50000:
                    logger.warning(f"Text too long ({len(raw_text)} chars), truncating to 50k")
                    raw_text = raw_text[:50000] + "\n\n[... truncated for processing ...]"

                all_text.append(raw_text)
                file_results.append({
                    "filename": filename,
                    "status": "success",
                    "text_length": len(raw_text),
                })

            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")
                file_results.append({
                    "filename": filename,
                    "status": "error",
                    "error": str(e),
                })
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

        combined_text = "\n\n".join(all_text)
        if not combined_text.strip():
            return jsonify({
                "error": "No text could be extracted from any file",
                "files": file_results,
            }), 400

        logger.info(f"Total extracted text: {len(combined_text)} characters")

        # ========== STEP 2: GEMINI AI PROCESSING ==========
        try:
            text_for_llm = combined_text[:20000]
            logger.info("🤖 Sending to Gemini AI for processing...")
            structured = llm_clean_and_structure(text_for_llm, summary_level=summary_level)
            
            gemini_concepts = structured.get("bullet_points", [])
            gemini_relations = structured.get("relations", [])
            
            logger.info(f"✅ Gemini provided {len(gemini_concepts)} concepts, {len(gemini_relations)} relationships")
            
        except Exception as e:
            logger.error(f"⚠️ Gemini processing failed: {e}")
            structured = {
                "clean_text": combined_text[:10000],
                "summary": "Text extracted successfully. AI structuring unavailable.",
                "bullet_points": [],
                "relations": [],
            }
            gemini_concepts = []
            gemini_relations = []

        clean_text = structured.get("clean_text") or combined_text[:50000]

        # ========== STEP 3: EXTRACT KEY CONCEPTS ==========
        keyphrases = []
        
        if gemini_concepts:
            for i, concept in enumerate(gemini_concepts[:top_k]):
                concept_clean = concept.strip()
                if len(concept_clean) >= 3:
                    keyphrases.append({
                        "phrase": concept_clean,
                        "score": 1.0 - (i * 0.05)
                    })
            logger.info(f"✅ Using {len(keyphrases)} concepts from Gemini")
        
        if not keyphrases:
            try:
                logger.info("📊 Falling back to spaCy NLP...")
                nlp_model = get_nlp()
                doc = nlp_model(clean_text[:30000])
                keyphrases = extract_keyphrases(doc, top_k=top_k)
                
                filtered = []
                seen = set()
                for kp in keyphrases:
                    phrase = (kp.get("phrase") or "").strip()
                    if phrase and len(phrase) >= 3 and phrase.lower() not in seen:
                        seen.add(phrase.lower())
                        filtered.append(kp)
                
                keyphrases = filtered
                logger.info(f"✅ NLP extracted {len(keyphrases)} concepts")
                
            except Exception as e:
                logger.error(f"❌ NLP also failed: {e}")
                keyphrases = []

        if not keyphrases:
            logger.warning("⚠️ No concepts extracted, using generic fallback")
            keyphrases = [
                {"phrase": "Document Overview", "score": 1.0},
                {"phrase": "Main Topics", "score": 0.8},
                {"phrase": "Key Points", "score": 0.6},
            ]

        # ========== STEP 4: BUILD MINDMAP WITH GEMINI ==========
        try:
            logger.info("🧠 Building mindmap with Gemini AI...")
            
            gemini_mindmap = extract_mindmap_with_gemini(clean_text, max_concepts=15)
            
            if gemini_mindmap and gemini_mindmap.get('central'):
                graph = nx.DiGraph()
                central = gemini_mindmap['central']
                graph.add_node(central)
                
                for branch in gemini_mindmap.get('branches', []):
                    branch_name = branch.get('name', '')
                    if branch_name:
                        graph.add_node(branch_name)
                        graph.add_edge(central, branch_name)
                        
                        for sub in branch.get('subs', []):
                            if sub:
                                graph.add_node(sub)
                                graph.add_edge(branch_name, sub)
                
                logger.info(f"✅ Built mindmap from Gemini: {len(graph.nodes())} nodes")
            else:
                raise Exception("Gemini mindmap structure invalid")
                
        except Exception as e:
            logger.warning(f"⚠️ Gemini mindmap failed: {e}, using concept-based structure")
            
            graph = nx.DiGraph()
            
            if keyphrases and len(keyphrases) > 0:
                root = keyphrases[0]["phrase"]
                graph.add_node(root)
                
                level1 = [kp["phrase"] for kp in keyphrases[1:5]]
                for branch in level1:
                    graph.add_node(branch)
                    graph.add_edge(root, branch)
                
                remaining = [kp["phrase"] for kp in keyphrases[5:]]
                if level1:
                    for idx, sub in enumerate(remaining):
                        parent = level1[idx % len(level1)]
                        graph.add_node(sub)
                        graph.add_edge(parent, sub)
            else:
                graph.add_node("Content")

        logger.info(f"📊 Final graph: {len(graph.nodes())} nodes, {len(graph.edges())} edges")

        # ========== STEP 5: CONVERT TO VIS.JS FORMAT WITH SANITIZATION ==========
        node_list = list(graph.nodes())
        node_to_id = {node: str(i) for i, node in enumerate(node_list)}

        def sanitize_label(label):
            """Clean label to prevent JavaScript regex errors"""
            if not label:
                return "Node"
            
            label = str(label)
            
            # Remove problematic regex special characters
            label = label.replace('(', '').replace(')', '')
            label = label.replace('[', '').replace(']', '')
            label = label.replace('{', '').replace('}', '')
            label = label.replace('/', ' ').replace('\\', ' ')
            label = label.replace('$', '').replace('^', '')
            label = label.replace('*', '').replace('+', '')
            label = label.replace('?', '').replace('|', '')
            
            # Truncate if too long
            if len(label) > 50:
                label = label[:47] + "..."
            
            # Clean up spaces
            label = ' '.join(label.split())
            
            return label.strip() if label.strip() else "Node"

        mindmap_data = {
            "nodes": [
                {
                    "id": node_to_id[node], 
                    "label": sanitize_label(node)
                }
                for node in node_list
            ],
            "edges": [
                {
                    "from": node_to_id[u], 
                    "to": node_to_id[v], 
                    "label": ""
                }
                for u, v in graph.edges()
            ],
        }

        logger.info(f"📊 Mindmap data prepared: {len(mindmap_data['nodes'])} nodes, {len(mindmap_data['edges'])} edges")
        
        # Debug: Show sample labels
        if mindmap_data['nodes']:
            sample_labels = [n['label'] for n in mindmap_data['nodes'][:3]]
            logger.info(f"Sample labels: {sample_labels}")

        # ========== STEP 6: PREPARE RESPONSE ==========
        response_data = {
            "text": clean_text[:5000],
            "summary": structured.get("summary", "")[:1000],
            "keyphrases": keyphrases[:top_k],
            "mindmap": mindmap_data,
            "meta": {
                "ocr_engine": ocr_engine,
                "files_processed": len(file_results),
                "files_success": sum(1 for f in file_results if f["status"] == "success"),
                "total_chars": len(combined_text),
                "concept_count": len(keyphrases),
                "graph_nodes": len(node_list),
                "graph_edges": len(graph.edges()),
                "used_gemini_concepts": len(gemini_concepts) > 0,
                "used_gemini_mindmap": gemini_mindmap is not None if 'gemini_mindmap' in locals() else False,
            },
            "files": file_results,
        }

        logger.info(f"✅ Processing complete! {len(mindmap_data['nodes'])} nodes, {len(keyphrases)} concepts")
        return jsonify(response_data), 200

    except Exception as e:
        logger.exception(f"❌ Critical processing error: {e}")
        return jsonify({
            "error": str(e),
            "type": type(e).__name__,
        }), 500

@app.route("/api/export/pdf", methods=["POST"])
def api_export_pdf():
    """Export mindmap results as comprehensive PDF report"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        logger.info("📄 Generating PDF export...")
        
        pdf_bytes = export_results_to_pdf(data)
        
        logger.info(f"✅ PDF exported: {len(pdf_bytes)} bytes")
        
        return pdf_bytes, 200, {
            'Content-Type': 'application/pdf',
            'Content-Disposition': 'attachment; filename=mindmap-results.pdf',
            'Content-Length': len(pdf_bytes),
        }
        
    except Exception as e:
        logger.error(f"❌ PDF export error: {e}")
        return jsonify({"error": str(e)}), 500
# ========== HEALTH CHECK ==========
@app.route("/api/health")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "frontend_dir": str(FRONTEND_DIR),
        "frontend_exists": FRONTEND_DIR.exists(),
        "gcv_ready": os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None,
        "gemini_ready": os.getenv("GEMINI_API_KEY") is not None
    }), 200

# ========== RUN APP ==========
if __name__ == "__main__":
    # Check credentials
    gcv_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if gcv_creds and Path(gcv_creds).exists():
        logger.info("✅ Google Vision credentials detected")
    else:
        logger.warning("⚠️ Google Vision credentials not found")
    
    if os.getenv("GEMINI_API_KEY"):
        logger.info("✅ Gemini API ready")
    else:
        logger.warning("⚠️ Gemini API key not set")
    
    if FRONTEND_DIR.exists():
        logger.info(f"✅ Frontend directory found: {FRONTEND_DIR}")
        html_files = list(FRONTEND_DIR.glob("*.html"))
        logger.info(f"   HTML files: {[f.name for f in html_files]}")
    else:
        logger.error(f"❌ Frontend directory not found: {FRONTEND_DIR}")
    
    logger.info(f"Require login for OCR: {os.getenv('REQUIRE_LOGIN', 'false').lower() == 'true'}")
    
    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000,
        use_reloader=True
    )
