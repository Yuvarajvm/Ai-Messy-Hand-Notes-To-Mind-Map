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

  function setStatus(msg) { if (statusEl) statusEl.textContent = msg || ''; }
  function setBusy(busy, label='Process') {
    if (!processBtn) return;
    processBtn.disabled = !!busy;
    processBtn.textContent = busy ? 'Processing…' : label;
  }

  function renderConcepts(list) {
    conceptsEl.innerHTML = '';
    (list || []).forEach(item => {
      const li = document.createElement('li');
      if (typeof item === 'string') li.textContent = item;
      else li.textContent = `${item.phrase || ''}${item.score != null ? ` (${Number(item.score).toFixed(2)})` : ''}`;
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
        color: { background: '#93c5fd', border: '#2563eb', highlight: { background: '#60a5fa', border: '#1d4ed8' } }
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
    const data = {
      nodes: new vis.DataSet(graph.nodes || []),
      edges: new vis.DataSet(graph.edges || [])
    };
    const opts = visOptions();
    if (hierarchical) {
      opts.layout = { hierarchical: { direction: 'LR', levelSeparation: 160, nodeSpacing: 80 } };
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
      const files = document.getElementById('files').files;
      if (!files || files.length === 0) {
        setStatus('Please select at least one file.');
        setBusy(false);
        return;
      }
      for (const f of files) fd.append('files', f);

      fd.append('lang', document.getElementById('lang').value || 'en');
      fd.append('top_k', document.getElementById('top_k').value || '15');
      fd.append('ocr_engine', document.getElementById('ocrEngine').value || 'gcv');
      if (document.getElementById('messy').checked) fd.append('messy', 'true');

      const res = await fetch('/api/process', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin'
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);

      // Text
      textEl.value = data.text || data.llm?.clean_text || '';

      // Concepts
      if (Array.isArray(data.keyphrases)) {
        renderConcepts(data.keyphrases);
      } else if (Array.isArray(data.llm?.concepts)) {
        renderConcepts(data.llm.concepts.map(c => ({ phrase: c, score: 1 })));
      }

      // Mindmap
      if (data.mindmap && mindmapEl) {
        mindmapNetwork = renderNetwork(mindmapEl, mindmapNetwork, {
          nodes: data.mindmap.nodes,
          edges: data.mindmap.edges
        }, false);
      }

      // Flowchart
      if (data.flowchart && flowchartEl) {
        flowchartNetwork = renderNetwork(flowchartEl, flowchartNetwork, {
          nodes: data.flowchart.nodes,
          edges: data.flowchart.edges
        }, false);
      }

      const meta = data.meta || {};
      setStatus(`Done (${meta.images_processed || 0} page(s), engine: ${meta.ocr_engine || 'n/a'})`);
    } catch (err) {
      console.error(err);
      setStatus(err.message || 'Failed to process');
    } finally {
      setBusy(false);
    }
  }

  if (form) form.addEventListener('submit', submitForm);
})();