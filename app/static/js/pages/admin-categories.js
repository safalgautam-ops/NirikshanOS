document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-categories-page]");
  if (!root) return;
  const dialog = root.querySelector("[data-category-dialog]");
  const title = root.querySelector("[data-category-title]");
  const error = root.querySelector("[data-category-error]");
  const save = root.querySelector("[data-category-save]");
  const saveLabel = root.querySelector("[data-category-save-label]");
  const fields = Object.fromEntries(Array.from(root.querySelectorAll("[data-category-field]")).map((field) => [field.dataset.categoryField, field]));
  let editingId = null;

  function setError(message = "") { error.textContent = message; error.hidden = !message; }
  function open(record = null) {
    editingId = record?.id || null;
    fields.name.value = record?.name || "";
    fields.description.value = record?.description || "";
    fields.sort_order.value = String(record?.sort_order ?? 0);
    title.textContent = editingId ? "Edit Category" : "New Category";
    setError();
    window.openAppDialog(dialog);
    fields.name.focus();
  }
  function close() { window.closeAppDialog(dialog); }

  root.addEventListener("click", async (event) => {
    if (event.target.closest("[data-category-new]")) return open();
    const edit = event.target.closest("[data-category-edit]");
    if (edit) { try { open(JSON.parse(edit.dataset.categoryEdit)); } catch { open(); } return; }
    if (event.target.closest("[data-category-close]")) return close();
    const remove = event.target.closest("[data-category-delete]");
    if (remove) {
      if (!confirm("Delete this category? Modules using it will lose their category.")) return;
      const response = await fetch(`/admin/categories/${remove.dataset.categoryDelete}`, { method: "DELETE", headers: { "X-CSRF-Token": window.getCsrfToken() } });
      if (response.ok) location.reload(); else window.toast?.error("Delete failed.");
      return;
    }
    if (!event.target.closest("[data-category-save]")) return;
    const form = { name: fields.name.value.trim(), description: fields.description.value, sort_order: fields.sort_order.value };
    if (!form.name) return setError("Name is required.");
    save.disabled = true; saveLabel.textContent = "Saving…"; setError();
    try {
      const response = await fetch(editingId ? `/admin/categories/${editingId}` : "/admin/categories/", {
        method: editingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": window.getCsrfToken() },
        body: JSON.stringify(form),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) return setError(data.error || "Save failed.");
      location.reload();
    } finally { save.disabled = false; saveLabel.textContent = "Save"; }
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !dialog.hidden) close(); });
});
