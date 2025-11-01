// frontend/app.js

(() => {

const form = document.getElementById('uploadForm');
const processBtn = document.getElementById('processBtn');
const statusEl = document.getElementById('status');
const textEl = document.getElementById('ocrText');
const conceptsEl = document.getElementById('concepts');
const mindmapEl = document.getElementById('mindmap');
const flowchartEl = document.getElementById('flowchart');

let mindmapNetwork = null;
let flowchartNetwork = null;

function setStatus(msg) { 
    if (statusEl) statusEl.textContent = msg || ''; 
}

function setBusy(busy, label='Process') {
    if (!processBtn) return;
    processBtn.disabled = !!busy;
    processBtn.textContent = busy ? 'Processing…' : label;
}

function renderConcepts(list) {
    if (!conceptsEl) return;
    conceptsEl.innerHTML = '';
    (list || []).forEach(item => {
        const li = document.createElement('li');
        if (typeof item === 'string') {
            li.textContent = item;
        } else {
            li.textContent = `${item.phrase || ''}${item.score != null ? ` (${Number(item.score).toFixed(2)})` : ''}`;
        }
        conceptsEl.appendChild(li);
    });
}

function visOptions() {
    return {
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            stabilization: { iterations: 200, fit: true }
        },
        nodes: {
            shape: 'dot',
            size: 14,
            font: { face: 'Inter, system-ui, sans-serif', size: 14, color: '#0f172a' },
            color: { 
                background: '#93c5fd', 
                border: '#2563eb', 
                highlight: { background: '#60a5fa', border: '#1d4ed8' } 
            }
        },
        edges: {
            color: { color: '#64748b', highlight: '#334155' },
            arrows: { to: { enabled: true, scaleFactor: 0.7 } },
            smooth: { enabled: false },
            font: { color: '#475569', size: 12, align: 'horizontal' }
        },
        interaction: { hover: true, tooltipDelay: 120 }
    };
}

function renderNetwork(container, previous, graph, hierarchical=false) {
    if (!container) return null;
    
    const data = {
        nodes: new vis.DataSet(graph.nodes || []),
        edges: new vis.DataSet(graph.edges || [])
    };
    
    const opts = visOptions();
    
    if (hierarchical) {
        opts.layout = { 
            hierarchical: { 
                direction: 'LR', 
                levelSeparation: 160, 
                nodeSpacing: 80 
            } 
        };
        opts.physics.enabled = false;
    }
    
    if (previous) previous.destroy();
    return new vis.Network(container, data, opts);
}

async function submitForm(e) {
    e.preventDefault();
    setStatus('');
    setBusy(true);
    
    try {
        const fd = new FormData();
        
        // Try both 'files' and 'fileInput' IDs for compatibility
        const filesInput = document.getElementById('files') || document.getElementById('fileInput');
        
        if (!filesInput || !filesInput.files || filesInput.files.length === 0) {
            setStatus('Please select at least one file.');
            setBusy(false);
            return;
        }
        
        const files = filesInput.files;
        
        for (const f of files) {
            fd.append('files', f);
        }
        
        // Append form parameters
        const langInput = document.getElementById('lang') || document.getElementById('ocrLang');
        const topKInput = document.getElementById('top_k') || document.getElementById('topConcepts');
        const ocrEngineInput = document.getElementById('ocrEngine');
        const messyInput = document.getElementById('messy') || document.getElementById('messyMode');
        
        fd.append('lang', langInput?.value || 'en');
        fd.append('top_k', topKInput?.value || '15');
        fd.append('ocr_engine', ocrEngineInput?.value || 'gcv');
        
        if (messyInput?.checked) {
            fd.append('messy', 'true');
        }
        
        // Make the request
        const res = await fetch('/api/process', {
            method: 'POST',
            body: fd,
            credentials: 'same-origin'
        });
        
        // ✅ CHECK RESPONSE STATUS FIRST (before parsing JSON)
        if (!res.ok) {
            const contentType = res.headers.get('content-type');
            
            // Try to parse as JSON if possible
            if (contentType && contentType.includes('application/json')) {
                try {
                    const errorData = await res.json();
                    throw new Error(errorData.error || `HTTP ${res.status}`);
                } catch (jsonErr) {
                    // If JSON parsing fails, get text
                    const errorText = await res.text();
                    throw new Error(`HTTP ${res.status}: ${errorText.substring(0, 200)}`);
                }
            } else {
                // Non-JSON error response
                const errorText = await res.text();
                throw new Error(`HTTP ${res.status}: ${errorText.substring(0, 200)}`);
            }
        }
        
        // ✅ NOW parse JSON (we know response is OK)
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await res.text();
            throw new Error(`Expected JSON response, got: ${text.substring(0, 100)}`);
        }
        
        const data = await res.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Display extracted text
        if (textEl) {
            textEl.value = data.text || data.llm?.clean_text || '';
        }
        
        // Display concepts
        if (Array.isArray(data.keyphrases)) {
            renderConcepts(data.keyphrases);
        } else if (Array.isArray(data.llm?.concepts)) {
            renderConcepts(data.llm.concepts.map(c => ({ phrase: c, score: 1 })));
        }
        
        // Render mindmap
        if (data.mindmap && mindmapEl) {
            mindmapNetwork = renderNetwork(mindmapEl, mindmapNetwork, {
                nodes: data.mindmap.nodes,
                edges: data.mindmap.edges
            }, false);
        }
        
        // Render flowchart
        if (data.flowchart && flowchartEl) {
            flowchartNetwork = renderNetwork(flowchartEl, flowchartNetwork, {
                nodes: data.flowchart.nodes,
                edges: data.flowchart.edges
            }, true); // Changed to true for hierarchical layout
        }
        
        const meta = data.meta || {};
        setStatus(`Done (${meta.images_processed || 0} page(s), engine: ${meta.ocr_engine || 'n/a'})`);
        
    } catch (err) {
        console.error('Processing error:', err);
        setStatus(err.message || 'Failed to process');
    } finally {
        setBusy(false);
    }
}

// Initialize form listener
if (form) {
    form.addEventListener('submit', submitForm);
} else {
    console.error('uploadForm not found in DOM');
}

})();
