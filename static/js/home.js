(function () {
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

  function currentRequestBody(force) {
    return {
      models: selectedModels(),
      prompt: document.getElementById("prompt").value,
      invoice_dir: document.getElementById("invoice-dir").value,
      ground_truth_dir: document.getElementById("ground-truth-dir").value,
      force,
    };
  }

  async function submitRun(force) {
    const models = selectedModels();
    if (models.length === 0) {
      alert("Select at least one model.");
      return;
    }
    document.getElementById("duplicate-warning").classList.add("hidden");

    const resp = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentRequestBody(force)),
    });

    if (resp.status === 409) {
      const err = await resp.json().catch(() => ({}));
      showDuplicateWarning(err.detail);
      return;
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      alert(`Failed to start run: ${err.detail || resp.statusText}`);
      return;
    }
    const data = await resp.json();
    window.location.href = `/runs/${data.run_id}`;
  }

  function showDuplicateWarning(detail) {
    const existing = detail.existing_run;
    const started = existing.started_at ? new Date(existing.started_at).toLocaleString() : new Date(existing.created_at).toLocaleString();
    const models = JSON.parse(existing.models_json).join(", ");
    document.getElementById("duplicate-message").textContent =
      `${detail.message} Existing run started ${started} with: ${models}.`;
    document.getElementById("duplicate-view-link").href = `/runs/${existing.id}`;
    document.getElementById("duplicate-warning").classList.remove("hidden");
    document.getElementById("duplicate-warning").scrollIntoView({ behavior: "smooth" });
  }

  document.addEventListener("DOMContentLoaded", () => {
    fetchModels();
    document.getElementById("start-run-btn").addEventListener("click", () => submitRun(false));
    document.getElementById("duplicate-force-btn").addEventListener("click", () => submitRun(true));
  });
})();
