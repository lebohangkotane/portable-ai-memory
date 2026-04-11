/**
 * PAM Content Script — ChatGPT
 * Injects a memory context banner above the ChatGPT conversation area.
 */

(async () => {
  // ChatGPT's main content area
  const MAIN_SELECTOR = "main";

  try {
    const main = await PAM.waitForEl(MAIN_SELECTOR, 12000);
    const ctx = await PAM.getContext("ChatGPT conversation");

    if (ctx && ctx.context && ctx.memory_count > 0) {
      PAM.injectBanner(ctx.context, main);
    }
  } catch (err) {
    // PAM API offline or element not found — fail silently
    console.debug("[PAM] ChatGPT injection skipped:", err.message);
  }
})();
