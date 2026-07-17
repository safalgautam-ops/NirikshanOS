function initListFilter() {
  const root = document.querySelector("[data-list-filter]");
  const input = root?.querySelector("[data-list-filter-input]");
  if (!input) return;

  const apply = () => {
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    root.querySelectorAll("[data-filter-text]").forEach((item) => {
      const match = !query || item.dataset.filterText.toLowerCase().includes(query);
      item.hidden = !match;
      if (match) visible += 1;
    });
    const empty = root.querySelector("[data-list-filter-empty]");
    if (empty) empty.hidden = visible !== 0;
  };

  input.addEventListener("input", apply);
  apply();
}

document.addEventListener("DOMContentLoaded", () => {
  initListFilter();
  const form = document.querySelector("[data-case-create]");
  if (!form) return;

  const dataNode = form.querySelector("[data-case-members]");
  const search = form.querySelector("[data-case-member-search]");
  const suggestions = form.querySelector("[data-case-member-suggestions]");
  const selectedList = form.querySelector("[data-case-selected-members]");
  const inputs = form.querySelector("[data-case-member-inputs]");
  let allMembers = [];
  let selected = [];
  try { allMembers = JSON.parse(dataNode?.textContent || "[]"); } catch { allMembers = []; }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function renderInputs() {
    inputs.replaceChildren(...selected.map((member) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "member_ids";
      input.value = member.id;
      return input;
    }));
  }

  function renderSelected() {
    selectedList.hidden = selected.length === 0;
    selectedList.innerHTML = selected.map((member) => `
      <div class="flex items-center gap-3 px-3 py-2" data-selected-member="${escapeHtml(member.id)}">
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium">${escapeHtml(member.name)}</div>
          <div class="truncate text-xs text-muted-foreground">${escapeHtml(member.email)}</div>
        </div>
        <span class="text-xs text-muted-foreground">${escapeHtml(member.role_name || "Member")}</span>
        <button type="button" class="text-muted-foreground hover:text-destructive" data-remove-member="${escapeHtml(member.id)}" aria-label="Remove">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-4"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
        </button>
      </div>`).join("");
    renderInputs();
  }

  function filteredMembers() {
    const query = search.value.trim().toLowerCase();
    const selectedIds = new Set(selected.map((member) => String(member.id)));
    return allMembers
      .filter((member) => !selectedIds.has(String(member.id)))
      .filter((member) => !query || String(member.name).toLowerCase().includes(query) || String(member.email).toLowerCase().includes(query))
      .slice(0, 8);
  }

  function renderSuggestions() {
    const members = filteredMembers();
    suggestions.hidden = members.length === 0 || document.activeElement !== search;
    suggestions.innerHTML = members.map((member) => `
      <button type="button" class="flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground" data-add-member="${escapeHtml(member.id)}">
        <span><span class="font-medium">${escapeHtml(member.name)}</span><span class="text-muted-foreground"> — ${escapeHtml(member.email)}</span></span>
      </button>`).join("");
  }

  search.addEventListener("focus", renderSuggestions);
  search.addEventListener("input", renderSuggestions);
  suggestions.addEventListener("mousedown", (event) => event.preventDefault());
  suggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-add-member]");
    if (!button) return;
    const member = allMembers.find((item) => String(item.id) === button.dataset.addMember);
    if (member && !selected.some((item) => String(item.id) === String(member.id))) selected.push(member);
    search.value = "";
    renderSelected();
    renderSuggestions();
    search.focus();
  });
  selectedList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-member]");
    if (!button) return;
    selected = selected.filter((member) => String(member.id) !== button.dataset.removeMember);
    renderSelected();
    renderSuggestions();
  });
  document.addEventListener("click", (event) => {
    if (!form.contains(event.target)) suggestions.hidden = true;
  });
});
