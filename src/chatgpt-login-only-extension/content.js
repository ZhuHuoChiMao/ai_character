(() => {
  const KEEP_TEXT = [
    "log in",
    "login",
    "sign in",
    "continue",
    "continue with google",
    "continue with microsoft",
    "continue with apple",
    "verify",
    "verification",
    "captcha",
    "human",
    "next",
    "登录",
    "登入",
    "继续",
    "验证",
    "人机",
    "下一步",
    "使用 google",
    "使用 microsoft",
    "使用 apple"
  ];

  const CHAT_SELECTORS = ["textarea", "div[contenteditable='true']", "[data-testid='prompt-textarea']"];

  function hasChatInput() {
    return CHAT_SELECTORS.some((selector) => {
      return [...document.querySelectorAll(selector)].some((node) => node.offsetParent !== null);
    });
  }

  function normalizedText(node) {
    return [
      node.innerText,
      node.textContent,
      node.getAttribute?.("aria-label"),
      node.getAttribute?.("title"),
      node.getAttribute?.("placeholder")
    ].filter(Boolean).join(" ").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function shouldKeep(node) {
    const text = normalizedText(node);
    return text && KEEP_TEXT.some((keyword) => text.includes(keyword));
  }

  function markKeepTree(node) {
    let current = node;
    let depth = 0;
    while (current && current !== document.body && depth < 6) {
      current.classList?.add("cgl-keep");
      current = current.parentElement;
      depth += 1;
    }
  }

  function focusLogin() {
    if (hasChatInput()) {
      document.documentElement.classList.remove("cgl-login-mode", "cgl-soft-mode");
      document.querySelectorAll(".cgl-keep").forEach((node) => node.classList.remove("cgl-keep"));
      return;
    }

    document.documentElement.classList.add("cgl-login-mode");
    document.querySelectorAll(".cgl-keep").forEach((node) => node.classList.remove("cgl-keep"));
    [...document.querySelectorAll("a, button, input, form, [role='button'], [aria-label], [data-testid]")]
      .filter(shouldKeep)
      .forEach(markKeepTree);

    document.documentElement.classList.toggle("cgl-soft-mode", document.querySelectorAll(".cgl-keep").length === 0);
  }

  function installBadge() {
    if (document.querySelector(".cgl-badge")) return;
    const badge = document.createElement("div");
    badge.className = "cgl-badge";
    badge.textContent = "Login Focus";
    document.documentElement.appendChild(badge);
  }

  const observer = new MutationObserver(() => {
    window.clearTimeout(window.__cglTimer);
    window.__cglTimer = window.setTimeout(focusLogin, 120);
  });

  installBadge();
  focusLogin();
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
