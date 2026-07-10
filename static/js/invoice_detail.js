(function () {
  const SPLIT_STORAGE_KEY = "invoiceDetailSplitPercent";
  const DEFAULT_PERCENT = 60;
  const MIN_PERCENT = 20;
  const MAX_PERCENT = 80;

  async function loadGroundTruth() {
    const pre = document.getElementById("ground-truth-content");
    if (!pre) return; // no ground-truth pane rendered (status was "missing")
    try {
      const resp = await fetch(`/api/ground-truth/${window.GROUND_TRUTH_FILENAME_URL}`);
      const text = await resp.text();
      try {
        pre.textContent = JSON.stringify(JSON.parse(text), null, 2);
      } catch (e) {
        pre.textContent = text; // not valid JSON syntax — show it raw so it's still inspectable
      }
    } catch (e) {
      pre.textContent = `Failed to load ground truth: ${e}`;
    }
  }

  function initSplitDrag() {
    const container = document.getElementById("detail-split");
    const invoicePane = document.getElementById("invoice-pane");
    const divider = document.getElementById("split-divider");
    if (!container || !invoicePane || !divider) return;

    // The initial split percentage is applied synchronously in an inline
    // <script> in invoice_detail.html, before the iframe/img is parsed — not
    // here. Re-applying it on DOMContentLoaded would run too late: the PDF
    // viewer inside the iframe computes its "fit" zoom once, at load time,
    // and does not reflow when the pane is resized afterward.
    function applyPercent(percent) {
      invoicePane.style.flexBasis = `${percent}%`;
    }

    let dragging = false;

    function percentFromEvent(e) {
      const rect = container.getBoundingClientRect();
      const raw = ((e.clientX - rect.left) / rect.width) * 100;
      return Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, raw));
    }

    function onPointerMove(e) {
      if (!dragging) return;
      applyPercent(percentFromEvent(e));
    }

    function onPointerUp(e) {
      if (!dragging) return;
      dragging = false;
      divider.classList.remove("dragging");
      document.body.style.userSelect = "";
      localStorage.setItem(SPLIT_STORAGE_KEY, String(percentFromEvent(e)));
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    }

    divider.addEventListener("pointerdown", (e) => {
      dragging = true;
      divider.classList.add("dragging");
      document.body.style.userSelect = "none"; // avoid selecting page text while dragging
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      e.preventDefault();
    });

    divider.addEventListener("dblclick", () => {
      applyPercent(DEFAULT_PERCENT);
      localStorage.removeItem(SPLIT_STORAGE_KEY);
    });

    // Keyboard support to match the divider's role="separator"
    divider.addEventListener("keydown", (e) => {
      const current = parseFloat(invoicePane.style.flexBasis) || DEFAULT_PERCENT;
      if (e.key === "ArrowLeft") {
        applyPercent(Math.max(MIN_PERCENT, current - 2));
        localStorage.setItem(SPLIT_STORAGE_KEY, invoicePane.style.flexBasis);
      } else if (e.key === "ArrowRight") {
        applyPercent(Math.min(MAX_PERCENT, current + 2));
        localStorage.setItem(SPLIT_STORAGE_KEY, invoicePane.style.flexBasis);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadGroundTruth();
    initSplitDrag();
  });
})();
