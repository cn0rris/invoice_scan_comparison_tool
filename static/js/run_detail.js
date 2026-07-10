(function () {
  const state = {
    runId: window.RUN_ID,
    rows: new Map(), // result_id -> {id, model_id, invoice_stem, status, mistake_count, error_message}
    ws: null,
  };

  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
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
      renderMeta(msg.run);
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
      document.getElementById("run-meta-status").textContent = msg.summary.status;
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

  function renderMeta(run) {
    document.getElementById("run-meta-started").textContent = new Date(run.started_at || run.created_at).toLocaleString();
    document.getElementById("run-meta-status").textContent = run.status;
    document.getElementById("run-meta-models").textContent = JSON.parse(run.models_json).join(", ");
    document.getElementById("run-meta-prompt").textContent = run.prompt_text;
    document.getElementById("run-meta-checksum").textContent = run.checksum || "(none)";
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

  function formatDuration(ms) {
    if (ms === null || ms === undefined) return "-";
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  }

  function renderSummary(summary) {
    document.getElementById("summary-panel").classList.remove("hidden");

    let perModelHtml = '<table class="summary-table"><thead><tr><th>Model</th><th>Total Mistakes</th><th>Success</th><th>Error</th><th>Avg Elapsed</th></tr></thead><tbody>';
    for (const [model, stats] of Object.entries(summary.per_model)) {
      perModelHtml += `<tr><td>${escapeHtml(model)}</td><td>${stats.total_mistakes}</td><td>${stats.success}</td><td>${stats.error}</td><td>${formatDuration(stats.avg_duration_ms)}</td></tr>`;
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
        const cell = summary.matrix[stem][m];
        if (!cell) {
          matrixHtml += "<td>-</td>";
          continue;
        }
        const mistakes = cell.mistake_count === null || cell.mistake_count === undefined ? "-" : cell.mistake_count;
        matrixHtml += `<td>${mistakes} <span class="muted">(${formatDuration(cell.duration_ms)})</span></td>`;
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

  async function init() {
    const resp = await fetch(`/api/runs/${state.runId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    for (const r of data.results) {
      state.rows.set(r.id, r);
    }
    renderMeta(data.run);
    updateProgress(data.run.completed_pairs, data.run.total_pairs);
    renderMatrix();
    if (data.run.status === "completed" || data.run.status === "failed") {
      const summaryResp = await fetch(`/api/runs/${state.runId}/summary`);
      renderSummary(await summaryResp.json());
    } else {
      connectWebSocket(state.runId);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initModalClose();
    init();
  });
})();
