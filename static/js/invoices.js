(function () {
  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function gtBadge(status) {
    const label = { valid: "✓ ground truth", invalid: "⚠ invalid ground truth", missing: "no ground truth" }[status] || status;
    const cls = { valid: "status-success", invalid: "status-error", missing: "status-pending" }[status] || "";
    return `<span class="${cls}">${escapeHtml(label)}</span>`;
  }

  async function loadInvoices() {
    const wrapper = document.getElementById("invoices-table-wrapper");
    try {
      const resp = await fetch("/api/invoices");
      const invoices = await resp.json();
      if (invoices.length === 0) {
        wrapper.innerHTML = '<p class="muted">No invoices yet — upload some above.</p>';
        return;
      }
      let html = '<table class="summary-table"><thead><tr><th>Filename</th><th>Size</th><th>Modified</th><th>Ground Truth</th></tr></thead><tbody>';
      for (const inv of invoices) {
        const url = `/api/invoices/${encodeURIComponent(inv.filename)}`;
        html += `<tr><td><a class="file-link" href="${url}" target="_blank" rel="noopener">${escapeHtml(inv.filename)}</a></td><td>${formatBytes(inv.size_bytes)}</td><td>${new Date(inv.modified_at).toLocaleString()}</td><td>${gtBadge(inv.ground_truth_status)}</td></tr>`;
      }
      html += "</tbody></table>";
      wrapper.innerHTML = html;
    } catch (e) {
      wrapper.innerHTML = `<p class="muted">Failed to load invoices: ${escapeHtml(String(e))}</p>`;
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    const input = document.getElementById("upload-input");
    const resultEl = document.getElementById("upload-result");
    if (!input.files.length) return;

    const formData = new FormData();
    for (const file of input.files) {
      formData.append("files", file);
    }

    const btn = document.getElementById("upload-btn");
    btn.disabled = true;
    try {
      const resp = await fetch("/api/invoices", { method: "POST", body: formData });
      const data = await resp.json();
      let html = "";
      if (data.saved.length) {
        html += `<p class="status-success">Uploaded: ${data.saved.map(escapeHtml).join(", ")}</p>`;
      }
      if (data.skipped.length) {
        html += '<p class="status-error">Skipped:</p><ul>';
        for (const s of data.skipped) {
          html += `<li>${escapeHtml(s.filename)} — ${escapeHtml(s.reason)}</li>`;
        }
        html += "</ul>";
      }
      resultEl.innerHTML = html;
      input.value = "";
      await loadInvoices();
    } catch (e) {
      resultEl.innerHTML = `<p class="status-error">Upload failed: ${escapeHtml(String(e))}</p>`;
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadInvoices();
    document.getElementById("upload-form").addEventListener("submit", handleUpload);
  });
})();
