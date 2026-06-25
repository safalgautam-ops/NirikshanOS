// Vanilla-JS toast manager - same visual language (classes, icons, colors)
// as the Base UI React Toast component this was ported from, but with no
// framework: this project is server-rendered Jinja + vanilla JS, so the
// stacked-card swipe-to-dismiss physics from the React version aren't
// reproduced here - toasts stack as a plain vertical list instead.
//
// Server-rendered pages hand off flash messages (the old `{% if error %}`
// banners) via a hidden `[data-flash]` element - see components/ui/toast.html's
// flash() macro - which this file scans for on load and turns into a toast,
// since CSP (script-src 'self', no 'unsafe-inline') rules out an inline
// <script> doing that directly.
(function () {
  const ICONS = {
    error:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
    info:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    loading:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>',
    success:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
    warning:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  };

  const ICON_COLOR_CLASS = {
    error: "text-destructive",
    info: "text-info",
    loading: "text-muted-foreground opacity-80",
    success: "text-success",
    warning: "text-warning",
  };

  const AUTO_DISMISS_MS = {
    error: 6000,
    info: 4000,
    success: 4000,
    warning: 5000,
    // loading has no auto-dismiss - the caller dismisses it explicitly
    // once whatever it was waiting on finishes.
  };

  let viewport = null;

  function getViewport() {
    if (viewport && document.body.contains(viewport)) return viewport;
    viewport = document.createElement("div");
    viewport.setAttribute("data-slot", "toast-viewport");
    viewport.className =
      "fixed inset-0 z-60 flex flex-col items-end justify-end gap-3 p-4 sm:p-8 pointer-events-none";
    document.body.appendChild(viewport);
    return viewport;
  }

  function dismiss(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.dataset.state = "closed";
    el.addEventListener("transitionend", () => el.remove(), { once: true });
    // Fallback in case the transitionend listener never fires (e.g. the
    // element had no visible transition to begin with).
    setTimeout(() => el.remove(), 300);
  }

  let nextId = 0;

  function show(type, title, description) {
    const id = `toast-${Date.now()}-${nextId++}`;
    const root = document.createElement("div");
    root.id = id;
    root.dataset.slot = "toast-root";
    root.dataset.type = type;
    root.dataset.state = "closed";
    root.className =
      "pointer-events-auto w-full max-w-90 rounded-lg border bg-popover text-popover-foreground shadow-lg/5 transition-all duration-300 ease-out data-[state=closed]:translate-y-2 data-[state=closed]:opacity-0 data-[state=open]:translate-y-0 data-[state=open]:opacity-100";

    const content = document.createElement("div");
    content.dataset.slot = "toast-content";
    content.className =
      "flex items-center justify-between gap-1.5 overflow-hidden px-3.5 py-3 text-sm";

    const left = document.createElement("div");
    left.className = "flex gap-2";

    if (ICONS[type]) {
      const iconWrap = document.createElement("div");
      iconWrap.dataset.slot = "toast-icon";
      iconWrap.className = `[&>svg]:h-lh [&>svg]:w-4 [&_svg]:pointer-events-none [&_svg]:shrink-0 ${ICON_COLOR_CLASS[type] || ""} ${type === "loading" ? "animate-spin" : ""}`;
      iconWrap.innerHTML = ICONS[type];
      left.appendChild(iconWrap);
    }

    const textWrap = document.createElement("div");
    textWrap.className = "flex flex-col gap-0.5";

    if (title) {
      const titleEl = document.createElement("p");
      titleEl.dataset.slot = "toast-title";
      titleEl.className = "font-medium";
      titleEl.textContent = title;
      textWrap.appendChild(titleEl);
    }

    if (description) {
      const descEl = document.createElement("p");
      descEl.dataset.slot = "toast-description";
      descEl.className = "text-muted-foreground";
      descEl.textContent = description;
      textWrap.appendChild(descEl);
    }

    left.appendChild(textWrap);
    content.appendChild(left);
    root.appendChild(content);
    getViewport().appendChild(root);

    // Flip to the open state on the next frame so the transition above
    // actually animates in, instead of starting already-visible.
    requestAnimationFrame(() => requestAnimationFrame(() => (root.dataset.state = "open")));

    const duration = AUTO_DISMISS_MS[type];
    if (duration) setTimeout(() => dismiss(id), duration);

    return id;
  }

  function scanFlashMessages() {
    document.querySelectorAll("[data-flash]").forEach((el) => {
      const type = el.dataset.flashType || "info";
      const message = el.dataset.flashMessage;
      if (message) show(type, null, message);
      el.remove();
    });
  }

  window.toast = {
    error: (description, title) => show("error", title, description),
    info: (description, title) => show("info", title, description),
    loading: (description, title) => show("loading", title, description),
    success: (description, title) => show("success", title, description),
    warning: (description, title) => show("warning", title, description),
    dismiss,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanFlashMessages);
  } else {
    scanFlashMessages();
  }
})();
