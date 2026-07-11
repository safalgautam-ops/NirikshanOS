// Universal runtime — loaded globally on every page.
// Contains: ui-runtime (dialogs/tabs/menus/etc.), toast, file-validate,
//           and the pageSearch Alpine component (drives the topbar search).
//
// NOTE: theme.js is kept separate because it must run synchronously
// before first paint to prevent a light/dark flash.

// ─── pageSearch Alpine component ────────────────────────────────────────────
// Drives the topbar "find on page" search, present on every authenticated page.
document.addEventListener("alpine:init", () => {
  Alpine.data("pageSearch", () => ({
    query: "",
    matches: [],
    currentIndex: -1,

    search() {
      this.clearHighlights();
      const term = this.query.trim();
      if (!term) {
        this.currentIndex = -1;
        return;
      }
      this._highlight(term);
      this.currentIndex = this.matches.length ? 0 : -1;
      this._focusCurrent();
    },

    _highlight(term) {
      const lowerTerm = term.toLowerCase();
      const skipTags = new Set([
        "SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE",
        "TEXTAREA", "INPUT", "SELECT", "MARK",
      ]);
      const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode(node) {
            const parent = node.parentElement;
            if (!parent || skipTags.has(parent.tagName))
              return NodeFilter.FILTER_REJECT;
            if (parent.closest("[data-page-search-ignore]"))
              return NodeFilter.FILTER_REJECT;
            if (parent.getClientRects().length === 0)
              return NodeFilter.FILTER_REJECT;
            if (!node.nodeValue.toLowerCase().includes(lowerTerm))
              return NodeFilter.FILTER_SKIP;
            return NodeFilter.FILTER_ACCEPT;
          },
        },
      );
      const textNodes = [];
      let node;
      while ((node = walker.nextNode())) textNodes.push(node);
      for (const textNode of textNodes)
        this._wrapMatches(textNode, term, lowerTerm);
    },

    _wrapMatches(textNode, term, lowerTerm) {
      const text = textNode.nodeValue;
      const lowerText = text.toLowerCase();
      const frag = document.createDocumentFragment();
      let cursor = 0;
      let idx = lowerText.indexOf(lowerTerm, cursor);
      while (idx !== -1) {
        if (idx > cursor)
          frag.appendChild(document.createTextNode(text.slice(cursor, idx)));
        const mark = document.createElement("mark");
        mark.className = "page-search-highlight";
        mark.textContent = text.slice(idx, idx + term.length);
        frag.appendChild(mark);
        this.matches.push(mark);
        cursor = idx + term.length;
        idx = lowerText.indexOf(lowerTerm, cursor);
      }
      if (cursor < text.length)
        frag.appendChild(document.createTextNode(text.slice(cursor)));
      textNode.parentNode.replaceChild(frag, textNode);
    },

    clearHighlights() {
      document.querySelectorAll("mark.page-search-highlight").forEach((mark) => {
        const parent = mark.parentNode;
        if (!parent) return;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
      });
      this.matches = [];
    },

    _focusCurrent() {
      this.matches.forEach((mark, i) =>
        mark.classList.toggle("page-search-current", i === this.currentIndex),
      );
      const current = this.matches[this.currentIndex];
      if (current) current.scrollIntoView({ behavior: "smooth", block: "center" });
    },

    next() {
      if (!this.matches.length) return;
      this.currentIndex = (this.currentIndex + 1) % this.matches.length;
      this._focusCurrent();
    },

    prev() {
      if (!this.matches.length) return;
      this.currentIndex =
        (this.currentIndex - 1 + this.matches.length) % this.matches.length;
      this._focusCurrent();
    },

    clear() {
      this.query = "";
      this.clearHighlights();
      this.currentIndex = -1;
    },
  }));
});

// ─── ui-runtime ─────────────────────────────────────────────────────────────
// Event-delegation runtime for app/templates/components/ui/*.html.
// No framework — data-slot attributes + one click/keydown listener on document.
(function () {
  const UI_READY = "uiReady";

  function all(root, selector) {
    return Array.from(root.querySelectorAll(selector));
  }

  function slot(name) {
    return `[data-slot="${name}"]`;
  }

  function setState(element, open) {
    if (!element) return;
    element.hidden = !open;
    element.dataset.state = open ? "open" : "closed";
  }

  function controlledBy(trigger, targetSlot) {
    const target =
      trigger.getAttribute("data-target") ||
      trigger.getAttribute("aria-controls");
    if (target) {
      const id = target.startsWith("#") ? target.slice(1) : target;
      const byId = document.getElementById(id);
      if (byId) return byId;
    }
    const container = trigger.closest(
      "[data-ui-root], [data-slot$='-root'], section, main, body",
    );
    const scoped = container?.querySelector(slot(targetSlot));
    if (scoped) return scoped;
    return document.querySelector(slot(targetSlot));
  }

  function openDialog(dialog) {
    if (!dialog) return;
    dialog.dataset.state = "open";
    if (dialog instanceof HTMLDialogElement) {
      if (!dialog.open) {
        try { dialog.showModal(); } catch { dialog.setAttribute("open", ""); }
      }
    } else {
      dialog.hidden = false;
    }
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    dialog.dataset.state = "closed";
    if (dialog instanceof HTMLDialogElement) {
      if (dialog.open) dialog.close();
    } else {
      dialog.hidden = true;
    }
  }

  function closeFloating(except) {
    all(
      document,
      [
        slot("menu-popup"), slot("menu-sub-popup"), slot("popover-popup"),
        slot("select-popup"), slot("combobox-popup"), slot("autocomplete-popup"),
        slot("tooltip-popup"),
      ].join(","),
    ).forEach((popup) => {
      if (except && (popup === except || popup.contains(except))) return;
      setState(popup, false);
    });
  }

  function initTabs(root) {
    if (root.dataset[UI_READY] === "tabs") return;
    root.dataset[UI_READY] = "tabs";

    const tabs = all(root, slot("tabs-tab"));
    const panels = all(root, `${slot("tabs-panel")}, ${slot("tabs-content")}`);
    let active = tabs.find((tab) => tab.dataset.state === "active") || tabs[0];
    if (!active) return;

    function activate(tab) {
      const value = tab.dataset.value || tab.textContent.trim();
      tabs.forEach((item) => {
        const selected = item === tab;
        item.dataset.state = selected ? "active" : "inactive";
        item.setAttribute("aria-selected", selected ? "true" : "false");
        item.tabIndex = selected ? 0 : -1;
      });
      panels.forEach((panel, index) => {
        const panelValue =
          panel.dataset.value ||
          tabs[index]?.dataset.value ||
          tabs[index]?.textContent.trim();
        const selected = panelValue === value;
        panel.hidden = !selected;
        panel.dataset.state = selected ? "active" : "inactive";
      });
      moveTabIndicator(tab);

      if (tab.dataset.saveForm !== undefined) {
        const saveButton = document.querySelector("[data-global-save-button]");
        if (saveButton) {
          if (tab.dataset.saveForm) {
            saveButton.setAttribute("form", tab.dataset.saveForm);
            saveButton.hidden = false;
          } else {
            saveButton.hidden = true;
          }
        }
      }
    }

    root.addEventListener("click", (event) => {
      const tab = event.target.closest(slot("tabs-tab"));
      if (!tab || !root.contains(tab)) return;
      activate(tab);
    });

    root.addEventListener("keydown", (event) => {
      if (!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"].includes(event.key))
        return;
      const current = event.target.closest(slot("tabs-tab"));
      if (!current || !root.contains(current)) return;
      event.preventDefault();
      const enabled = tabs.filter((tab) => !tab.disabled);
      const index = enabled.indexOf(current);
      const nextIndex =
        event.key === "Home" ? 0
        : event.key === "End" ? enabled.length - 1
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? (index - 1 + enabled.length) % enabled.length
          : (index + 1) % enabled.length;
      enabled[nextIndex]?.focus();
      if (enabled[nextIndex]) activate(enabled[nextIndex]);
    });

    activate(active);
  }

  function moveTabIndicator(tab) {
    const list = tab.closest(slot("tabs-list"));
    const indicator = list?.querySelector(slot("tab-indicator"));
    if (!list || !indicator) return;
    const isUnderline = list.dataset.variant === "underline";
    const tabRect = tab.getBoundingClientRect();
    const listRect = list.getBoundingClientRect();
    indicator.style.width = tabRect.width + "px";
    if (!isUnderline) indicator.style.height = tabRect.height + "px";
    const tx = tabRect.left - listRect.left;
    const ty = isUnderline
      ? tabRect.bottom - listRect.top - 2
      : tabRect.top - listRect.top;
    indicator.style.translate = tx + "px " + ty + "px";
  }

  function initDisclosure(root, itemSlot) {
    all(root, itemSlot).forEach((item) => {
      if (!(item instanceof HTMLDetailsElement)) return;
      item.dataset.state = item.open ? "open" : "closed";
      item.addEventListener("toggle", () => {
        item.dataset.state = item.open ? "open" : "closed";
      });
    });
  }

  function initFilter(root, inputSlot, itemSlot, emptySlot, statusSlot) {
    const input = root.querySelector(slot(inputSlot));
    if (!input || input.dataset[UI_READY]) return;
    input.dataset[UI_READY] = "filter";

    function update() {
      const query = input.value.trim().toLowerCase();
      let visible = 0;
      all(root, slot(itemSlot)).forEach((item) => {
        const text = (item.dataset.value || item.textContent).trim().toLowerCase();
        const matched = !query || text.includes(query);
        item.hidden = !matched;
        if (matched) visible += 1;
      });
      const empty = root.querySelector(slot(emptySlot));
      if (empty) empty.hidden = visible !== 0;
      const status = root.querySelector(slot(statusSlot));
      if (status) status.textContent = `${visible} result${visible === 1 ? "" : "s"}`;
    }

    input.addEventListener("input", update);
    update();
  }

  function initToast(toast) {
    if (toast.dataset[UI_READY]) return;
    toast.dataset[UI_READY] = "toast";
    const delay = Number(toast.dataset.duration || 0);
    if (delay > 0) {
      window.setTimeout(() => {
        toast.dataset.state = "closed";
        toast.hidden = true;
      }, delay);
    }
  }

  function positionCsMenu(trigger, popup) {
    const rect = trigger.getBoundingClientRect();
    const popupW = popup.offsetWidth || 224;
    const popupH = popup.scrollHeight || 200;
    let left = rect.right - popupW;
    let top = rect.bottom + 4;
    if (left < 8) left = 8;
    if (left + popupW > window.innerWidth - 8) left = window.innerWidth - popupW - 8;
    if (top + popupH > window.innerHeight - 8) top = rect.top - popupH - 4;
    popup.style.left = left + "px";
    popup.style.top = top + "px";
    popup.style.right = "auto";
    popup.style.bottom = "auto";
  }

  function closeCsMenus(except) {
    all(document, "[data-cs-open]").forEach((m) => {
      if (m !== except) {
        m.hidden = true;
        m.classList.add("hidden");
        delete m.dataset.csOpen;
      }
    });
  }

  document.addEventListener("click", (event) => {
    const target = event.target;

    const csMenuTrigger = target.closest("[data-cs-menu]");
    if (csMenuTrigger) {
      const menuId = csMenuTrigger.dataset.csMenu;
      const popup = document.getElementById(menuId);
      if (!popup) return;
      const isOpen = popup.dataset.csOpen === "1";
      closeCsMenus(isOpen ? null : popup);
      closeFloating();
      if (!isOpen) {
        popup.hidden = false;
        popup.classList.remove("hidden");
        popup.dataset.csOpen = "1";
        positionCsMenu(csMenuTrigger, popup);
      }
      return;
    }

    const modalTrigger = target.closest(
      `${slot("dialog-trigger")}, ${slot("alert-dialog-trigger")}, ${slot("sheet-trigger")}, ${slot("drawer-trigger")}, ${slot("command-dialog-trigger")}`,
    );
    if (modalTrigger) {
      const triggerSlot = modalTrigger.dataset.slot;
      const targetSlot = triggerSlot.replace("-trigger", "");
      openDialog(controlledBy(modalTrigger, targetSlot));
      return;
    }

    const close = target.closest(
      `${slot("dialog-close")}, ${slot("alert-dialog-close")}, ${slot("sheet-close")}, ${slot("drawer-close")}, ${slot("command-dialog-close")}, ${slot("popover-close")}`,
    );
    if (close) {
      const dialog = close.closest(
        "dialog, [data-slot='sheet'], [data-slot='drawer'], [data-slot='dialog'], [data-slot='alert-dialog'], [data-slot='command-dialog']",
      );
      if (dialog) {
        closeDialog(dialog);
      } else {
        setState(close.closest(slot("popover-popup")), false);
      }
      return;
    }

    const floatingTrigger = target.closest(
      `${slot("menu-trigger")}, ${slot("menu-sub-trigger")}, ${slot("popover-trigger")}, ${slot("select-trigger")}, ${slot("select-button")}, ${slot("combobox-trigger")}, ${slot("autocomplete-trigger")}, ${slot("tooltip-trigger")}`,
    );
    if (floatingTrigger) {
      const map = {
        "menu-trigger": "menu-popup",
        "menu-sub-trigger": "menu-sub-popup",
        "popover-trigger": "popover-popup",
        "select-trigger": "select-popup",
        "select-button": "select-popup",
        "combobox-trigger": "combobox-popup",
        "autocomplete-trigger": "autocomplete-popup",
        "tooltip-trigger": "tooltip-popup",
      };
      const popup = controlledBy(floatingTrigger, map[floatingTrigger.dataset.slot]);
      const open = popup?.hidden;
      closeFloating(popup);
      setState(popup, Boolean(open));
      floatingTrigger.setAttribute("aria-expanded", Boolean(open).toString());
      return;
    }

    const selectItem = target.closest(slot("select-item"));
    if (selectItem) {
      const select = selectItem.closest(slot("select"));
      const value = selectItem.dataset.value || selectItem.textContent.trim();
      all(select || document, slot("select-item")).forEach((item) => {
        const selected = item === selectItem;
        item.toggleAttribute("data-selected", selected);
        item.setAttribute("aria-selected", selected ? "true" : "false");
      });
      const display = select?.querySelector(slot("select-value"));
      if (display) display.textContent = selectItem.textContent.trim();
      const hidden = select?.querySelector("input[type='hidden']");
      if (hidden) {
        hidden.value = value;
        hidden.dispatchEvent(new Event("change", { bubbles: true }));
        const form = hidden.closest("form");
        if (form && form.method.toLowerCase() === "get") form.submit();
      }
      closeFloating();
      return;
    }

    const clear = target.closest(
      `${slot("combobox-clear")}, ${slot("autocomplete-clear")}`,
    );
    if (clear) {
      const root = clear.closest(`${slot("combobox")}, ${slot("autocomplete")}`);
      const input = root?.querySelector("input");
      if (input) {
        input.value = "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
      }
      return;
    }

    if (!target.closest("[data-slot$='-popup'], [data-slot$='-trigger']")) {
      closeFloating();
    }
    if (!target.closest("[data-cs-open]") && !target.closest("[data-cs-menu]")) {
      closeCsMenus();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeFloating();
    closeCsMenus();
    all(document, "dialog[data-state='open'], dialog[open]").forEach(closeDialog);
  });

  function scanUiRuntime() {
    all(document, slot("tabs")).forEach(initTabs);
    all(document, slot("accordion")).forEach((root) =>
      initDisclosure(root, slot("accordion-item")),
    );
    all(document, slot("collapsible")).forEach((root) =>
      initDisclosure(root.parentElement || document, slot("collapsible")),
    );
    all(document, slot("combobox")).forEach((root) =>
      initFilter(root, "combobox-input", "combobox-item", "combobox-empty", "combobox-status"),
    );
    all(document, slot("autocomplete")).forEach((root) =>
      initFilter(root, "autocomplete-input", "autocomplete-item", "autocomplete-empty", "autocomplete-status"),
    );
    all(document, slot("command")).forEach((root) =>
      initFilter(root, "command-input", "command-item", "command-empty", "command-status"),
    );
    all(
      document,
      `${slot("menu-popup")}, ${slot("menu-sub-popup")}, ${slot("popover-popup")}, ${slot("select-popup")}, ${slot("combobox-popup")}, ${slot("autocomplete-popup")}, ${slot("tooltip-popup")}`,
    ).forEach((popup) => {
      if (!popup.dataset.state) setState(popup, false);
    });
    all(document, slot("toast-popup")).forEach(initToast);
  }

  scanUiRuntime();
  window.addEventListener("app-router:patch", scanUiRuntime);
})();

// ─── toast ───────────────────────────────────────────────────────────────────
// Vanilla-JS toast manager. Scans for [data-flash] elements on load and
// turns them into toasts. Exposes window.toast.{error,info,success,warning,loading,dismiss}.
(function () {
  const ICONS = {
    error:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
    info:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    loading: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>',
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
    warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  };
  const ICON_COLOR_CLASS = {
    error: "text-destructive", info: "text-info",
    loading: "text-muted-foreground opacity-80", success: "text-success", warning: "text-warning",
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
