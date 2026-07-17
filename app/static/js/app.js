// Apply the saved theme before first paint.
if (localStorage.theme === "light") document.documentElement.classList.remove("dark");

document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      document.documentElement.classList.toggle("dark");
      localStorage.theme = document.documentElement.classList.contains("dark") ? "dark" : "light";
    });
  }
});

window.getCsrfToken = function () {
  return document.querySelector('meta[name="csrf-token"]')?.content || "";
};

window.openAppDialog = function (dialog) {
  if (!dialog) return;
  dialog.hidden = false;
  dialog.dataset.state = "open";
  if (dialog instanceof HTMLDialogElement && !dialog.open) {
    try { dialog.showModal(); } catch { dialog.setAttribute("open", ""); }
  }
};

window.closeAppDialog = function (dialog) {
  if (!dialog) return;
  dialog.dataset.state = "closed";
  if (dialog instanceof HTMLDialogElement && dialog.open) dialog.close();
  else dialog.hidden = true;
};

// Find text in the current server-rendered page.
(function () {
  function initPageSearch(root) {
    const input = root.querySelector("[data-page-search-input]");
    const count = root.querySelector("[data-page-search-count]");
    if (!input) return;
    let matches = [];
    let currentIndex = -1;

    function clearHighlights() {
      document.querySelectorAll("mark.page-search-highlight").forEach((mark) => {
        const parent = mark.parentNode;
        if (!parent) return;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
      });
      matches = [];
      currentIndex = -1;
    }

    function focusCurrent() {
      matches.forEach((mark, index) => mark.classList.toggle("page-search-current", index === currentIndex));
      matches[currentIndex]?.scrollIntoView({ behavior: "smooth", block: "center" });
      if (count) count.textContent = matches.length ? `${currentIndex + 1}/${matches.length}` : "No results";
    }

    function wrapMatches(textNode, term) {
      const text = textNode.nodeValue;
      const lowerText = text.toLowerCase();
      const lowerTerm = term.toLowerCase();
      const fragment = document.createDocumentFragment();
      let cursor = 0;
      let index = lowerText.indexOf(lowerTerm);
      while (index !== -1) {
        if (index > cursor) fragment.append(document.createTextNode(text.slice(cursor, index)));
        const mark = document.createElement("mark");
        mark.className = "page-search-highlight";
        mark.textContent = text.slice(index, index + term.length);
        fragment.append(mark);
        matches.push(mark);
        cursor = index + term.length;
        index = lowerText.indexOf(lowerTerm, cursor);
      }
      if (cursor < text.length) fragment.append(document.createTextNode(text.slice(cursor)));
      textNode.parentNode.replaceChild(fragment, textNode);
    }

    function search() {
      clearHighlights();
      const term = input.value.trim();
      root.querySelector("[data-page-search-controls]")?.toggleAttribute("hidden", !term);
      if (!term) return;
      const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "TEXTAREA", "INPUT", "SELECT", "MARK"]);
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skipTags.has(parent.tagName) || parent.closest("[data-page-search-ignore]")) return NodeFilter.FILTER_REJECT;
          if (!parent.getClientRects().length || !node.nodeValue.toLowerCase().includes(term.toLowerCase())) return NodeFilter.FILTER_SKIP;
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((node) => wrapMatches(node, term));
      currentIndex = matches.length ? 0 : -1;
      focusCurrent();
    }

    input.addEventListener("input", search);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (!matches.length) return;
        currentIndex = event.shiftKey
          ? (currentIndex - 1 + matches.length) % matches.length
          : (currentIndex + 1) % matches.length;
        focusCurrent();
      }
      if (event.key === "Escape") {
        input.value = "";
        search();
      }
    });
    root.querySelector("[data-page-search-next]")?.addEventListener("click", () => {
      if (!matches.length) return;
      currentIndex = (currentIndex + 1) % matches.length;
      focusCurrent();
    });
    root.querySelector("[data-page-search-prev]")?.addEventListener("click", () => {
      if (!matches.length) return;
      currentIndex = (currentIndex - 1 + matches.length) % matches.length;
      focusCurrent();
    });
    root.querySelector("[data-page-search-clear]")?.addEventListener("click", () => {
      input.value = "";
      search();
      input.focus();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-page-search]").forEach(initPageSearch);
    document.querySelectorAll("[data-submit-form]").forEach((input) => {
      input.addEventListener("change", () => document.getElementById(input.dataset.submitForm)?.submit());
    });
    document.querySelectorAll("form[data-auto-submit]").forEach((form) => form.submit());
  });
})();

// ─── ui-runtime ─────────────────────────────────────────────────────────────
// Small event-delegation layer for the Jinja macros used by this project.
(function () {
  const slot = (name) => `[data-slot="${name}"]`;
  const all = (root, selector) => Array.from(root.querySelectorAll(selector));

  function setOpen(element, open) {
    if (!element) return;
    element.hidden = !open;
    element.dataset.state = open ? "open" : "closed";
    if (!open && element.__positionCleanup) element.__positionCleanup();
  }

  function targetFor(trigger, targetSlot) {
    const target = trigger.dataset.target || trigger.getAttribute("aria-controls");
    if (target) {
      const found = document.getElementById(target.replace(/^#/, ""));
      if (found) return found;
    }
    const scope = trigger.closest("[data-ui-root], [data-slot$='-root'], section, main, body");
    return scope?.querySelector(slot(targetSlot)) || document.querySelector(slot(targetSlot));
  }

  const popupSelector = ["menu-popup", "select-popup"]
    .map(slot)
    .join(",");

  function closePopups(except) {
    all(document, popupSelector).forEach((popup) => {
      if (except && (popup === except || popup.contains(except))) return;
      setOpen(popup, false);
    });
  }

  function positionSelect(trigger, popup) {
    if (!trigger || !popup || popup.dataset.slot !== "select-popup") return;
    popup.style.position = "fixed";
    popup.style.margin = "0";
    popup.style.minWidth = `${trigger.offsetWidth}px`;

    const reposition = () => {
      const rect = trigger.getBoundingClientRect();
      const viewportHeight = document.documentElement.clientHeight;
      const popupHeight = popup.getBoundingClientRect().height;
      const openUp = viewportHeight - rect.bottom < popupHeight + 8 && rect.top > viewportHeight - rect.bottom;
      popup.style.left = `${rect.left}px`;
      popup.style.top = openUp ? "auto" : `${rect.bottom + 4}px`;
      popup.style.bottom = openUp ? `${viewportHeight - rect.top + 4}px` : "auto";
    };

    const hidden = popup.hidden;
    const visibility = popup.style.visibility;
    popup.style.visibility = "hidden";
    popup.hidden = false;
    reposition();
    popup.hidden = hidden;
    popup.style.visibility = visibility;

    if (popup.__positionCleanup) popup.__positionCleanup();
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    popup.__positionCleanup = () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
      popup.__positionCleanup = null;
    };
  }

  function initTabs(root) {
    if (root.dataset.uiReady) return;
    root.dataset.uiReady = "tabs";
    const tabs = all(root, slot("tabs-tab"));
    const panels = all(root, `${slot("tabs-panel")}, ${slot("tabs-content")}`);
    if (!tabs.length) return;

    const activate = (tab) => {
      const value = tab.dataset.value || tab.textContent.trim();
      tabs.forEach((item) => {
        const active = item === tab;
        item.dataset.state = active ? "active" : "inactive";
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
      });
      panels.forEach((panel, index) => {
        const panelValue = panel.dataset.value || tabs[index]?.dataset.value || tabs[index]?.textContent.trim();
        const active = panelValue === value;
        panel.hidden = !active;
        panel.dataset.state = active ? "active" : "inactive";
      });

      const list = tab.closest(slot("tabs-list"));
      const indicator = list?.querySelector(slot("tab-indicator"));
      if (list && indicator) {
        const tabRect = tab.getBoundingClientRect();
        const listRect = list.getBoundingClientRect();
        const underline = list.dataset.variant === "underline";
        indicator.style.width = `${tabRect.width}px`;
        if (!underline) indicator.style.height = `${tabRect.height}px`;
        indicator.style.translate = `${tabRect.left - listRect.left}px ${underline ? tabRect.bottom - listRect.top - 2 : tabRect.top - listRect.top}px`;
      }

      if (tab.dataset.saveForm !== undefined) {
        const save = document.querySelector("[data-global-save-button]");
        if (save) {
          save.hidden = !tab.dataset.saveForm;
          if (tab.dataset.saveForm) save.setAttribute("form", tab.dataset.saveForm);
        }
      }
    };

    root.addEventListener("click", (event) => {
      const tab = event.target.closest(slot("tabs-tab"));
      if (tab && root.contains(tab)) activate(tab);
    });
    root.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      const current = event.target.closest(slot("tabs-tab"));
      if (!current || !root.contains(current)) return;
      const enabled = tabs.filter((tab) => !tab.disabled);
      const index = enabled.indexOf(current);
      const next = event.key === "Home" ? 0
        : event.key === "End" ? enabled.length - 1
        : ["ArrowLeft", "ArrowUp"].includes(event.key)
          ? (index - 1 + enabled.length) % enabled.length
          : (index + 1) % enabled.length;
      event.preventDefault();
      enabled[next]?.focus();
      if (enabled[next]) activate(enabled[next]);
    });

    activate(tabs.find((tab) => tab.dataset.state === "active") || tabs[0]);
  }

  function initCommand(root) {
    const input = root.querySelector(slot("command-input"));
    if (!input || input.dataset.uiReady) return;
    input.dataset.uiReady = "command";
    const update = () => {
      const query = input.value.trim().toLowerCase();
      all(root, slot("command-item")).forEach((item) => {
        item.hidden = Boolean(query) && !(item.dataset.value || item.textContent).toLowerCase().includes(query);
      });
    };
    input.addEventListener("input", update);
    update();
  }

  function positionContextMenu(trigger, popup) {
    const rect = trigger.getBoundingClientRect();
    const width = popup.offsetWidth || 224;
    const height = popup.scrollHeight || 200;
    let left = Math.max(8, rect.right - width);
    let top = rect.bottom + 4;
    if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
    if (top + height > window.innerHeight - 8) top = rect.top - height - 4;
    Object.assign(popup.style, { left: `${left}px`, top: `${top}px`, right: "auto", bottom: "auto" });
  }

  function closeContextMenus(except) {
    all(document, "[data-cs-open]").forEach((menu) => {
      if (menu === except) return;
      menu.hidden = true;
      menu.classList.add("hidden");
      delete menu.dataset.csOpen;
    });
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    const contextTrigger = target.closest("[data-cs-menu]");
    if (contextTrigger) {
      const popup = document.getElementById(contextTrigger.dataset.csMenu);
      if (!popup) return;
      const open = popup.dataset.csOpen === "1";
      closeContextMenus(open ? null : popup);
      closePopups();
      if (!open) {
        popup.hidden = false;
        popup.classList.remove("hidden");
        popup.dataset.csOpen = "1";
        positionContextMenu(contextTrigger, popup);
      }
      return;
    }

    const dialogTrigger = target.closest(slot("dialog-trigger"));
    if (dialogTrigger) {
      window.openAppDialog(targetFor(dialogTrigger, "dialog"));
      return;
    }

    // Sheets (the mobile sidebar drawer) dismiss on a backdrop click, unlike
    // the confirm/edit dialogs above - clicking outside a real <dialog> lands
    // a click on the dialog element itself (its ::backdrop), never on a
    // descendant, so this only fires when nothing inside was clicked.
    if (target.matches('dialog[data-slot="sheet"]')) {
      window.closeAppDialog(target);
      return;
    }

    const dialogClose = target.closest(slot("dialog-close"));
    if (dialogClose) {
      window.closeAppDialog(dialogClose.closest("dialog, [data-slot='dialog']"));
      return;
    }

    const popupTrigger = target.closest(`${slot("menu-trigger")}, ${slot("select-trigger")}`);
    if (popupTrigger) {
      const popupSlot = popupTrigger.dataset.slot === "select-trigger" ? "select-popup" : "menu-popup";
      const popup = targetFor(popupTrigger, popupSlot);
      const open = Boolean(popup?.hidden);
      closePopups(popup);
      if (open) positionSelect(popupTrigger, popup);
      setOpen(popup, open);
      popupTrigger.setAttribute("aria-expanded", String(open));
      return;
    }

    const item = target.closest(slot("select-item"));
    if (item && !item.hasAttribute("data-disabled")) {
      const select = item.closest(slot("select"));
      const value = item.dataset.value || item.textContent.trim();
      all(select || document, slot("select-item")).forEach((option) => {
        const selected = option === item;
        option.toggleAttribute("data-selected", selected);
        option.setAttribute("aria-selected", String(selected));
        const marker = option.firstElementChild;
        if (marker) marker.textContent = selected ? "✓" : "";
      });
      const display = select?.querySelector(slot("select-value"));
      if (display) {
        display.textContent = item.textContent.trim();
        display.removeAttribute("data-placeholder");
      }
      const input = select?.querySelector("input[type='hidden']");
      if (input) {
        input.value = value;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        const form = input.closest("form");
        if (form?.method.toLowerCase() === "get") form.submit();
      }
      closePopups();
      return;
    }

    if (!target.closest("[data-slot$='-popup'], [data-slot$='-trigger']")) closePopups();
    if (!target.closest("[data-cs-open], [data-cs-menu]")) closeContextMenus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closePopups();
    closeContextMenus();
    all(document, "dialog[open]").forEach(window.closeAppDialog);
  });

  function scan() {
    all(document, slot("tabs")).forEach(initTabs);
    all(document, slot("command")).forEach(initCommand);
    all(document, popupSelector).forEach((popup) => {
      if (!popup.dataset.state) setOpen(popup, false);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan, { once: true });
  else scan();
})();

// ─── toast ───────────────────────────────────────────────────────────────────
// Vanilla-JS toast manager. Scans for [data-flash] elements on load and
// turns them into toasts. Exposes the error/info methods used by page controllers.
(function () {
  const ICONS = {
    error:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
    info:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
    warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  };
  const ICON_COLOR_CLASS = {
    error: "text-destructive", info: "text-info",
    success: "text-success", warning: "text-warning",
  };
  const AUTO_DISMISS_MS = { error: 6000, info: 4000, success: 4000, warning: 5000 };

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
    content.className = "flex items-center justify-between gap-1.5 overflow-hidden px-3.5 py-3 text-sm";

    const left = document.createElement("div");
    left.className = "flex gap-2";

    if (ICONS[type]) {
      const iconWrap = document.createElement("div");
      iconWrap.dataset.slot = "toast-icon";
      iconWrap.className = `[&>svg]:h-lh [&>svg]:w-4 [&_svg]:pointer-events-none [&_svg]:shrink-0 ${ICON_COLOR_CLASS[type] || ""}`;
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
    error:   (description, title) => show("error", title, description),
    info:    (description, title) => show("info", title, description),
    success: (description, title) => show("success", title, description),
    warning: (description, title) => show("warning", title, description),
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanFlashMessages);
  } else {
    scanFlashMessages();
  }
})();

// ─── file-validate ───────────────────────────────────────────────────────────
// Rejects oversized files before upload via data-max-size-bytes on <input type="file">.
(function () {
  function formatMB(bytes) {
    return `${(bytes / (1024 * 1024)).toFixed(0)}MB`;
  }

  function validate(input) {
    const max = Number(input.dataset.maxSizeBytes);
    if (!max || !input.files) return true;
    const label = input.dataset.maxSizeLabel || formatMB(max);
    for (const file of input.files) {
      if (file.size > max) {
        window.toast.error(`"${file.name}" is ${formatMB(file.size)} - max is ${label}.`);
        input.value = "";
        return false;
      }
    }
    return true;
  }

  document.addEventListener("change", (event) => {
    const input = event.target;
    if (input.matches && input.matches('input[type="file"][data-max-size-bytes]')) {
      validate(input);
    }
  }, true);

  document.addEventListener("submit", (event) => {
    const inputs = event.target.querySelectorAll('input[type="file"][data-max-size-bytes]');
    for (const input of inputs) {
      if (!validate(input)) {
        event.preventDefault();
        return;
      }
    }
  }, true);
})();
