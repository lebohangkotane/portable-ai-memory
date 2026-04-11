/**
 * PAM Background Service Worker
 * Fetches context from the local PAM API (localhost:8765) and caches it.
 * Relays messages from content scripts to the API.
 */

const PAM_API = "http://localhost:8765";
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

let _contextCache = null;
let _contextCachedAt = 0;

async function fetchContext(summary = "") {
  const now = Date.now();
  if (_contextCache && (now - _contextCachedAt) < CACHE_TTL_MS && !summary) {
    return _contextCache;
  }
  const url = `${PAM_API}/context?summary=${encodeURIComponent(summary)}&token_budget=1500`;
  const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
  if (!resp.ok) throw new Error(`PAM API error: ${resp.status}`);
  const data = await resp.json();
  if (!summary) {
    _contextCache = data;
    _contextCachedAt = now;
  }
  return data;
}

async function addMemory(content, memory_type = "fact", tags = []) {
  const resp = await fetch(`${PAM_API}/memories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, memory_type, tags }),
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error(`PAM API error: ${resp.status}`);
  return resp.json();
}

// Check API health on startup and set badge
chrome.runtime.onStartup.addListener(async () => {
  try {
    await fetch(`${PAM_API}/health`, { signal: AbortSignal.timeout(3000) });
    chrome.action.setBadgeText({ text: "" });
  } catch {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#cc0000" });
  }
});

// Handle messages from content scripts and popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "GET_CONTEXT") {
    fetchContext(msg.summary || "")
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true; // keep channel open for async response
  }

  if (msg.type === "ADD_MEMORY") {
    addMemory(msg.content, msg.memory_type || "fact", msg.tags || [])
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (msg.type === "INVALIDATE_CACHE") {
    _contextCache = null;
    _contextCachedAt = 0;
    sendResponse({ ok: true });
    return false;
  }
});
