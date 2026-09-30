// Small browser helpers used by the Brython pages (streaming fetch + safe markdown).
window.matini = {
  // Render assistant markdown to sanitized HTML. Falls back to escaped text if the
  // CDN libraries failed to load.
  renderMarkdown(text) {
    if (window.marked && window.DOMPurify) {
      return window.DOMPurify.sanitize(window.marked.parse(text, { breaks: true }));
    }
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, "<br>");
  },

  // Upload one File as multipart/form-data (field "file"). common.request() can only send JSON.
  // Callbacks: onOk(rawResponseText) on success, onErr(message) otherwise; exactly one is called.
  async uploadFile(url, file, onOk, onErr) {
    let text = null;
    let failure = null;
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(url, { method: "POST", body: form });
      text = await resp.text();
      if (!resp.ok) {
        let detail = resp.statusText;
        try { detail = JSON.parse(text).detail || detail; } catch (e) {}
        failure = typeof detail === "string" ? detail : JSON.stringify(detail);
      }
    } catch (e) {
      failure = "ติดต่อ API ไม่ได้";
    }
    if (failure !== null) onErr(failure);
    else onOk(text);
  },

  // Radar of the NIST function scores (0-5) on the assessment page. Labels/scores come from the
  // canvas data-* attributes; a null score is an unscored function and is left as a gap.
  // No-op when there is no report (no canvas) or Chart.js failed to load (the bars still show).
  renderFunctionRadar(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !window.Chart) return;
    const labels = JSON.parse(canvas.dataset.labels || "[]");
    const scores = JSON.parse(canvas.dataset.scores || "[]");
    const font = { family: "Inter, sans-serif" };
    new window.Chart(canvas, {
      type: "radar",
      data: {
        labels,
        datasets: [{
          label: "คะแนน",
          data: scores,
          spanGaps: false,
          borderColor: "#6366f1",
          backgroundColor: "rgba(99, 102, 241, 0.18)",
          borderWidth: 2,
          pointBackgroundColor: "#6366f1",
          pointRadius: 3,
          pointHoverRadius: 5,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          r: {
            min: 0,
            max: 5,
            ticks: { stepSize: 1, backdropColor: "transparent", color: "#94a3b8", font: { ...font, size: 10 } },
            pointLabels: { color: "#334155", font: { ...font, size: 11, weight: "600" } },
            grid: { color: "#e2e8f0" },
            angleLines: { color: "#e2e8f0" },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => (ctx.raw === null || ctx.raw === undefined ? "ยังไม่มีคะแนน" : `${ctx.raw}/5`),
            },
          },
        },
      },
    });
  },

  // POST JSON and read an NDJSON response line by line.
  // Callbacks: onLine(rawLineString) for each non-empty line, onEnd(errorMessageOrNull) exactly once.
  async streamNdjson(url, body, onLine, onEnd) {
    let failure = null;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        let detail = resp.statusText;
        try { detail = (await resp.json()).detail || detail; } catch (e) {}
        throw new Error(`HTTP ${resp.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 1);
          if (line) onLine(line);
        }
      }
      if (buffer.trim()) onLine(buffer.trim());
    } catch (e) {
      failure = String(e.message || e);
    }
    onEnd(failure);
  },
};
