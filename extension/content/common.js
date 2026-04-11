/**
 * PAM Common Content Script
 * Shared utilities injected into ChatGPT and Gemini pages.
 */

window.PAM = window.PAM || {};

/**
 * Fetch context from PAM vault via background worker.
 * @param {string} summary - brief description of the current conversation topic
 * @returns {Promise<{context: string, memory_count: number, token_estimate: number}>}
 */
PAM.getContext = function (summary = "") {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "GET_CONTEXT", summary }, (resp) => {
      if (chrome.runtime.lastError) {
        return reject(new Error(chrome.runtime.lastError.message));
      }
      if (resp && resp.ok) resolve(resp.data);
      else reject(new Error(resp?.error || "PAM not reachable — is 'pam api' running?"));
    });
  });
};

/**
 * Save a new memory to the vault.
 * @param {string} content
 * @param {string} memory_type - fact | preference | skill | goal | instruction
 * @param {string[]} tags
 */
PAM.addMemory = function (content, memory_type = "fact", tags = []) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      { type: "ADD_MEMORY", content, memory_type, tags },
      (resp) => {
        if (chrome.runtime.lastError) {
          return reject(new Error(chrome.runtime.lastError.message));
        }
        if (resp && resp.ok) resolve(resp.data);
        else reject(new Error(resp?.error || "Could not save memory"));
      }
    );
  });
};

/**
 * Inject a non-intrusive context banner at the top of a container element.
 * If a banner already exists it is not duplicated.
 */
PAM.injectBanner = function (contextText, targetEl) {
  if (!targetEl || document.getElementById("pam-context-banner")) return;

  const banner = document.createElement("div");
  banner.id = "pam-context-banner";
  banner.style.cssText = [
    "background: #1a1a2e",
    "color: #c8d3f5",
    "padding: 8px 14px",
    "font-size: 11px",
    "font-family: 'Fira Mono', 'Cascadia Code', monospace",
    "border-bottom: 1px solid #2a2a4a",
    "white-space: pre-wrap",
    "max-height: 100px",
    "overflow-y: auto",
    "line-height: 1.5",
    "z-index: 9999",
    "position: relative",
  ].join(";");

  const label = document.createElement("span");
  label.style.cssText = "color: #82aaff; font-weight: bold; margin-right: 8px;";
  label.textContent = "PAM";

  const preview = contextText.length > 350
    ? contextText.slice(0, 350) + "…"
    : contextText;

  banner.appendChild(label);
  banner.appendChild(document.createTextNode(preview));

  // Dismiss button
  const dismiss = document.createElement("button");
  dismiss.textContent = "×";
  dismiss.style.cssText = [
    "float: right",
    "background: none",
    "border: none",
    "color: #82aaff",
    "cursor: pointer",
    "font-size: 14px",
    "line-height: 1",
    "padding: 0 4px",
  ].join(";");
  dismiss.title = "Dismiss PAM context";
  dismiss.addEventListener("click", () => banner.remove());
  banner.prepend(dismiss);

  targetEl.prepend(banner);
};

/**
 * Wait for a DOM element matching a CSS selector, up to a timeout.
 * @param {string} selector
 * @param {number} timeoutMs
 * @returns {Promise<Element>}
 */
PAM.waitForEl = function (selector, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(selector);
    if (existing) return resolve(existing);

    const observer = new MutationObserver(() => {
      const found = document.querySelector(selector);
      if (found) {
        observer.disconnect();
        resolve(found);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => {
      observer.disconnect();
      reject(new Error(`PAM: element "${selector}" not found within ${timeoutMs}ms`));
    }, timeoutMs);
  });
};
