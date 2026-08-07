// --- Signature hero element: a typed-out pipeline trace ---
const TRACE_LINES = [
  "> POST /emails/classify",
  '{ subject: "Refund needed", body: "Third crash this week..." }',
  "",
  "[stage 1] received ................ ok",
  "[stage 2] classifying via claude ... ",
  '  -> category: support | priority: high | sentiment: negative',
  "[stage 3] drafting reply ........... ",
  '  -> "Hi there, I\'m sorry the app has let you down..."',
  "[stage 4] send ..................... DRY_RUN (nothing sent)",
  "",
  "done in 1.8s",
];

const terminalEl = document.getElementById("terminal");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runTerminal() {
  if (!terminalEl) return;
  if (reduceMotion) {
    terminalEl.textContent = TRACE_LINES.join("\n");
    return;
  }
  terminalEl.textContent = "";
  for (const line of TRACE_LINES) {
    let built = "";
    for (const ch of line) {
      built += ch;
      terminalEl.textContent = terminalEl.textContent.replace(/[^\n]*$/, built);
      await sleep(10);
    }
    terminalEl.textContent += "\n";
    await sleep(150);
  }
}

runTerminal();

// --- Live demo form: calls a locally running API instance ---
const API_BASE = "http://127.0.0.1:8000";
const form = document.getElementById("demoForm");
const output = document.getElementById("output");

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const subject = document.getElementById("subject").value;
    const body = document.getElementById("body").value;

    output.textContent = "Sending request to " + API_BASE + " ...";

    try {
      const res = await fetch(`${API_BASE}/emails/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, body }),
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }

      const data = await res.json();
      output.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      output.textContent =
        "Could not reach the API.\n\n" +
        "Make sure the backend is running:\n" +
        "  uv run uvicorn app.main:app --reload\n\n" +
        "Error detail: " + err.message;
    }
  });
}
