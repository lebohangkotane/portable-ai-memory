const API = "http://localhost:8765";

async function checkStatus() {
  const dot = document.getElementById("status-dot");
  const apiStatus = document.getElementById("api-status");
  try {
    const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      dot.className = "dot dot-online";
      apiStatus.textContent = "API online";
      return true;
    }
  } catch {}
  dot.className = "dot dot-offline";
  apiStatus.textContent = "Offline — run: pam api";
  return false;
}

async function loadStats() {
  try {
    const r = await fetch(`${API}/stats`, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById("mem-count").textContent = `${d.total_memories} memories`;
    document.getElementById("conv-count").textContent = `${d.total_conversations} conversations`;
  } catch {}
}

document.getElementById("copy-btn").addEventListener("click", async () => {
  const btn = document.getElementById("copy-btn");
  const feedback = document.getElementById("copy-feedback");
  try {
    const r = await fetch(`${API}/context?token_budget=1500`, { signal: AbortSignal.timeout(5000) });
    if (!r.ok) throw new Error("API error");
    const d = await r.json();
    if (!d.context) throw new Error("No context available");
    await navigator.clipboard.writeText(d.context);
    feedback.textContent = "Copied!";
    btn.textContent = "Copied!";
    setTimeout(() => {
      feedback.textContent = "";
      btn.textContent = "Copy my context";
    }, 2000);
  } catch (err) {
    feedback.textContent = err.message.includes("No context") ? "No memories yet" : "API offline";
    setTimeout(() => { feedback.textContent = ""; }, 2500);
  }
});

document.getElementById("save-btn").addEventListener("click", async () => {
  const content = document.getElementById("memory-input").value.trim();
  const memory_type = document.getElementById("memory-type").value;
  const feedback = document.getElementById("save-feedback");

  if (!content) {
    feedback.style.color = "#ff757f";
    feedback.textContent = "Enter something to save";
    setTimeout(() => { feedback.textContent = ""; }, 2000);
    return;
  }

  try {
    const r = await fetch(`${API}/memories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, memory_type }),
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error("Save failed");

    document.getElementById("memory-input").value = "";
    feedback.style.color = "#c3e88d";
    feedback.textContent = "Saved!";
    setTimeout(() => { feedback.textContent = ""; }, 2000);

    // Invalidate the context cache so next injection is fresh
    chrome.runtime.sendMessage({ type: "INVALIDATE_CACHE" });
    loadStats();
  } catch (err) {
    feedback.style.color = "#ff757f";
    feedback.textContent = "Could not save — is pam api running?";
    setTimeout(() => { feedback.textContent = ""; }, 3000);
  }
});

// Init
checkStatus().then(online => { if (online) loadStats(); });
