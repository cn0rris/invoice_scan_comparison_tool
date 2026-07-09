(function () {
  const state = {
    runId: null,
    rows: new Map(), // result_id -> {id, model_id, invoice_stem, status, mistake_count, error_message}
    ws: null,
  };

  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  async function fetchModels() {
    const container = document.getElementById("ollama-models");
    try {
      const resp = await fetch("/api/models");
      const data = await resp.json();
      if (!data.ollama.available) {
        container.innerHTML = `<p class="muted">Ollama not reachable${data.ollama.error ? ": " + escapeHtml(data.ollama.error) : ""} — is it running natively on the host?</p>`;
        return;
      }
      if (data.ollama.models.length === 0) {
        container.innerHTML = '<p class="muted">Ollama is reachable but no models are pulled.</p>';
        return;
      }
      container.innerHTML = data.ollama.models
        .map(
          (m) => `<label class="checkbox-row"><input type="checkbox" name="model" value="${escapeHtml(m)}" /> ${escapeHtml(m)}</label>`
        )
        .join("");
    } catch (e) {
      container.innerHTML = `<p class="muted">Failed to load Ollama models: ${escapeHtml(String(e))}</p>`;
    }
  }

  function selectedModels() {
    return Array.from(document.querySelectorAll('input[name="model"]:checked')).map((el) => el.value);
  }

  async function submitRun() {
    const models = selectedModels();
    if (models.length === 0) {
      alert("Select at least one model.");
      return;
    }
    const prompt = document.getElementById("prompt").value;
    const invoiceDir = document.getElementById("invoice-dir").value;
    const groundTruthDir = document.getElementById("ground-truth-dir").value;

    const resp = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ models, prompt, invoice_dir: invoiceDir, ground_truth_dir: groundTruthDir }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      alert(`Failed to start run: ${err.detail || resp.statusText}`);
      return;
    }
    const data = await resp.json();
    history.replaceState(null, "", `?run=${data.run_id}`);
    beginRun(data.run_id);
  }

  function beginRun(runId) {
    state.runId = runId;
    state.rows = new Map();
    document.getElementById("progress-panel").classList.remove("hidden");
    document.getElementById("summary-panel").classList.add("hidden");
    connectWebSocket(runId);
  }

  function connectWebSocket(runId) {
    if (state.ws) {
      state.ws.close();
    }
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/runs/${runId}`);
    state.ws = ws;
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    };
  }

  function handleMessage(msg) {
    if (msg.type === "snapshot") {
      for (const r of msg.results) {
        state.rows.set(r.id, r);
      }
      updateProgress(msg.run.completed_pairs, msg.run.total_pairs);
      renderMatrix();
      if (msg.summary) {
        renderSummary(msg.summary);
      }
    } else if (msg.type === "result_update") {
      const existing = state.rows.get(msg.result_id) || {};
      state.rows.set(msg.result_id, { ...existing, id: msg.result_id, ...msg });
      renderMatrix();
    } else if (msg.type === "progress") {
      updateProgress(msg.completed, msg.total);
    } else if (msg.type === "run_complete") {
      renderSummary(msg.summary);
    } else if (msg.type === "error") {
      alert(msg.message);
    }
  }

  function updateProgress(completed, total) {
    document.getElementById("progress-text").textContent = `${completed} / ${total} complete`;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    document.getElementById("progress-bar-fill").style.width = `${pct}%`;
  }

  function statusIcon(status) {
    return { success: "✓", error: "✗", running: "…", pending: "·", no_ground_truth: "n/a" }[status] || status;
  }

  function renderMatrix() {
    const rows = Array.from(state.rows.values());
    const invoiceStems = Array.from(new Set(rows.map((r) => r.invoice_stem))).sort();
    const modelIds = Array.from(new Set(rows.map((r) => r.model_id))).sort();

    let html = '<table class="live-table"><thead><tr><th>Invoice</th>';
    for (const m of modelIds) html += `<th>${escapeHtml(m)}</th>`;
    html += "</tr></thead><tbody>";
    for (const stem of invoiceStems) {
      html += `<tr><td>${escapeHtml(stem)}</td>`;
      for (const m of modelIds) {
        const row = rows.find((r) => r.invoice_stem === stem && r.model_id === m);
        if (!row) {
          html += "<td>-</td>";
          continue;
        }
        const label =
          row.status === "success"
            ? `${statusIcon(row.status)} ${row.mistake_count} mistake${row.mistake_count === 1 ? "" : "s"}`
            : statusIcon(row.status);
        html += `<td class="status-${row.status} cell-clickable" data-result-id="${row.id}">${escapeHtml(label)}</td>`;
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    document.getElementById("live-table-wrapper").innerHTML = html;

    document.querySelectorAll("#live-table-wrapper td.cell-clickable").forEach((td) => {
      td.addEventListener("click", () => showDetail(td.dataset.resultId));
    });
  }

  async function showDetail(resultId) {
    const resp = await fetch(`/api/runs/${state.runId}`);
    const data = await resp.json();
    const row = data.results.find((r) => r.id === resultId);
    if (!row) return;
    let diffLines = [];
    if (row.diff_json) {
      const diff = JSON.parse(row.diff_json);
      diffLines = diff.mismatches.map((m) => `- [${m.mismatch_type}] ${m.message}`);
    }
    const body = [
      `Model: ${row.model_id}`,
      `Invoice: ${row.invoice_filename}`,
      `Status: ${row.status}`,
      row.error_message ? `Error: ${row.error_message}` : null,
      "",
      "Mismatches:",
      diffLines.length ? diffLines.join("\n") : "(none)",
      "",
      "Parsed output:",
      row.parsed_json ? JSON.stringify(JSON.parse(row.parsed_json), null, 2) : "(none)",
      "",
      "Raw model output:",
      row.raw_output || "(none)",
    ]
      .filter((l) => l !== null)
      .join("\n");
    document.getElementById("detail-modal-body").textContent = body;
    document.getElementById("detail-modal").classList.remove("hidden");
  }

  function renderSummary(summary) {
    document.getElementById("summary-panel").classList.remove("hidden");

    let perModelHtml = '<table class="summary-table"><thead><tr><th>Model</th><th>Total Mistakes</th><th>Success</th><th>Error</th></tr></thead><tbody>';
    for (const [model, stats] of Object.entries(summary.per_model)) {
      perModelHtml += `<tr><td>${escapeHtml(model)}</td><td>${stats.total_mistakes}</td><td>${stats.success}</td><td>${stats.error}</td></tr>`;
    }
    perModelHtml += "</tbody></table>";
    document.getElementById("summary-per-model").innerHTML = perModelHtml;

    const modelIds = Object.keys(summary.per_model).sort();
    const invoiceStems = Object.keys(summary.matrix).sort();
    let matrixHtml = '<table class="summary-table"><thead><tr><th>Invoice</th>';
    for (const m of modelIds) matrixHtml += `<th>${escapeHtml(m)}</th>`;
    matrixHtml += "</tr></thead><tbody>";
    for (const stem of invoiceStems) {
      matrixHtml += `<tr><td>${escapeHtml(stem)}</td>`;
      for (const m of modelIds) {
        const val = summary.matrix[stem][m];
        matrixHtml += `<td>${val === null || val === undefined ? "-" : val}</td>`;
      }
      matrixHtml += "</tr>";
    }
    matrixHtml += "</tbody></table>";
    document.getElementById("summary-matrix").innerHTML = matrixHtml;
  }

  function initModalClose() {
    document.getElementById("detail-modal-close").addEventListener("click", () => {
      document.getElementById("detail-modal").classList.add("hidden");
    });
    document.getElementById("detail-modal").addEventListener("click", (e) => {
      if (e.target.id === "detail-modal") {
        document.getElementById("detail-modal").classList.add("hidden");
      }
    });
  }

  async function initFromUrl() {
    const params = new URLSearchParams(location.search);
    const runId = params.get("run");
    if (!runId) return;
    state.runId = runId;
    const resp = await fetch(`/api/runs/${runId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    for (const r of data.results) {
      state.rows.set(r.id, r);
    }
    document.getElementById("progress-panel").classList.remove("hidden");
    updateProgress(data.run.completed_pairs, data.run.total_pairs);
    renderMatrix();
    if (data.run.status === "completed" || data.run.status === "failed") {
      const summaryResp = await fetch(`/api/runs/${runId}/summary`);
      renderSummary(await summaryResp.json());
    } else {
      connectWebSocket(runId);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    fetchModels();
    initModalClose();
    document.getElementById("start-run-btn").addEventListener("click", submitRun);
    initFromUrl();
  });
})();
