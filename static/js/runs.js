(function () {
  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  async function loadRuns() {
    const wrapper = document.getElementById("runs-table-wrapper");
    try {
      const resp = await fetch("/api/runs");
      const runs = await resp.json();
      if (runs.length === 0) {
        wrapper.innerHTML = '<p class="muted">No runs yet — start one from the Home page.</p>';
        return;
      }
      let html = '<table class="summary-table"><thead><tr><th>Started</th><th>Status</th><th>Models</th><th>Progress</th></tr></thead><tbody>';
      for (const run of runs) {
        const models = JSON.parse(run.models_json).join(", ");
        const started = run.started_at ? new Date(run.started_at).toLocaleString() : new Date(run.created_at).toLocaleString();
        html += `<tr class="cell-clickable" data-run-id="${run.id}">
          <td>${escapeHtml(started)}</td>
          <td class="status-${run.status}">${escapeHtml(run.status)}</td>
          <td>${escapeHtml(models)}</td>
          <td>${run.completed_pairs} / ${run.total_pairs}</td>
        </tr>`;
      }
      html += "</tbody></table>";
      wrapper.innerHTML = html;
      wrapper.querySelectorAll("tr[data-run-id]").forEach((row) => {
        row.classList.add("cell-clickable");
        row.addEventListener("click", () => {
          window.location.href = `/runs/${row.dataset.runId}`;
        });
      });
    } catch (e) {
      wrapper.innerHTML = `<p class="muted">Failed to load runs: ${escapeHtml(String(e))}</p>`;
    }
  }

  document.addEventListener("DOMContentLoaded", loadRuns);
})();
