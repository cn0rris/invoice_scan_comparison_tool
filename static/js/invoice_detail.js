(function () {
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

  document.addEventListener("DOMContentLoaded", loadGroundTruth);
})();
