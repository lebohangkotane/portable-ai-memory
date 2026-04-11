/**
 * PAM Content Script — Google Gemini
 * Injects a memory context banner above the Gemini conversation area.
 */

(async () => {
  // Gemini's conversation container — try multiple selectors in order
  const SELECTORS = [
    "chat-window",
    ".conversation-container",
    "main",
  ];

  async function findContainer() {
    for (const sel of SELECTORS) {
      try {
        const el = await PAM.waitForEl(sel, 3000);
        if (el) return el;
      } catch {
        // try next selector
      }
    }
    throw new Error("Could not find Gemini conversation container");
  }

  try {
    const container = await findContainer();
    const ctx = await PAM.getContext("Gemini conversation");

    if (ctx && ctx.context && ctx.memory_count > 0) {
      PAM.injectBanner(ctx.context, container);
    }
  } catch (err) {
    console.debug("[PAM] Gemini injection skipped:", err.message);
  }
})();
