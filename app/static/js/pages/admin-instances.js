document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-instances-page]");
  if (!root) return;
  const editDialog = root.querySelector("[data-instance-dialog]");
  const deleteDialog = root.querySelector("[data-instance-delete-dialog]");
  const fields = Object.fromEntries([...root.querySelectorAll("[data-instance-field]")].map((el) => [el.dataset.instanceField, el]));
  const editTitle = root.querySelector("[data-instance-title]");
  const editError = root.querySelector("[data-instance-error]");
  const saveButton = root.querySelector("[data-instance-save]");
  const saveLabel = root.querySelector("[data-instance-save-label]");
  const deleteError = root.querySelector("[data-instance-delete-error]");
  const deleteLoading = root.querySelector("[data-instance-delete-loading]");
  const deleteUsageBox = root.querySelector("[data-instance-delete-usage]");
  const testRunsBlock = root.querySelector("[data-instance-test-runs-block]");
  const testRunsText = root.querySelector("[data-instance-test-runs]");
  const impact = root.querySelector("[data-instance-delete-impact]");
  const clearButton = root.querySelector("[data-instance-clear-runs]");
  const clearLabel = root.querySelector("[data-instance-clear-label]");
  const deleteButton = root.querySelector("[data-instance-delete-confirm]");
  const deleteLabel = root.querySelector("[data-instance-delete-label]");
  let editingId = null;
  let deleteTarget = null;
  let deleteUsage = null;

  const defaults = { id:"", display_name:"", image_tag:"", cpu_limit:"1.0", memory_limit:"512m", pids_limit:"128", queue_name:"medium_queue", default_timeout_seconds:"120" };
  function setTextError(node, message="") { node.textContent = message; node.hidden = !message; }
  function parseRecord(value) { try { return JSON.parse(value); } catch { return null; } }

  function openEdit(record = null) {
    editingId = record?.id || null;
    const values = { ...defaults, ...(record || {}) };
    for (const [name, field] of Object.entries(fields)) field.value = String(values[name] ?? "");
    fields.id.disabled = Boolean(editingId);
    editTitle.textContent = editingId ? "Edit Instance" : "New Instance";
    saveLabel.textContent = editingId ? "Save" : "Register";
    setTextError(editError);
    openAppDialog(editDialog);
    (editingId ? fields.display_name : fields.id).focus();
  }
  const closeEdit = () => closeAppDialog(editDialog);
  const closeDelete = () => closeAppDialog(deleteDialog);

  function renderUsage() {
    deleteLoading.hidden = true;
    deleteUsageBox.hidden = !deleteUsage;
    const runs = Number(deleteUsage?.test_runs || 0);
    testRunsBlock.hidden = runs === 0;
    testRunsText.textContent = String(runs);
    const parts = [];
    if (Number(deleteUsage?.modules || 0) > 0) parts.push(`unassign ${deleteUsage.modules} module(s)`);
    if (Number(deleteUsage?.plans || 0) > 0) parts.push(`remove access from ${deleteUsage.plans} plan(s)`);
    impact.hidden = runs > 0;
    impact.textContent = `This will ${parts.length ? parts.join(" and ") : "change nothing else — no modules or plans currently reference it"}. This cannot be undone.`;
    deleteButton.disabled = runs > 0;
  }

  async function openDelete(record) {
    deleteTarget = record;
    deleteUsage = null;
    root.querySelector("[data-instance-delete-name]").textContent = record.display_name || record.id;
    setTextError(deleteError);
    deleteLoading.hidden = false;
    deleteUsageBox.hidden = true;
    deleteButton.disabled = true;
    openAppDialog(deleteDialog);
    try {
      const response = await fetch(`/admin/instances/${record.id}/usage`);
      deleteUsage = response.ok ? await response.json() : { modules:0, plans:0, test_runs:0 };
    } finally { renderUsage(); }
  }

  root.addEventListener("click", async (event) => {
    if (event.target.closest("[data-instance-new]")) return openEdit();
    const edit = event.target.closest("[data-instance-edit]");
    if (edit) return openEdit(parseRecord(edit.dataset.instanceEdit));
    if (event.target.closest("[data-instance-close]")) return closeEdit();
    const recheck = event.target.closest("[data-instance-recheck]");
    if (recheck) {
      const response = await fetch(`/admin/instances/${recheck.dataset.instanceRecheck}/recheck`, { method:"POST", headers:{"X-CSRF-Token":getCsrfToken()} }).catch(() => null);
      return response?.ok ? toast?.info("Recheck queued — refresh in a few seconds to see the updated status.") : toast?.error("Recheck request failed.");
    }
    const toggle = event.target.closest("[data-instance-toggle]");
    if (toggle) {
      const record = parseRecord(toggle.dataset.instanceToggle); if (!record) return;
      const response = await fetch(`/admin/instances/${record.id}`, { method:"PUT", headers:{"Content-Type":"application/json","X-CSRF-Token":getCsrfToken()}, body:JSON.stringify({...record,is_active:!record.is_active}) }).catch(() => null);
      return response?.ok ? location.reload() : toast?.error("Failed to update instance.");
    }
    const openDeleteButton = event.target.closest("[data-instance-delete-open]");
    if (openDeleteButton) { const record=parseRecord(openDeleteButton.dataset.instanceDeleteOpen); if(record) openDelete(record); return; }
    if (event.target.closest("[data-instance-delete-close]")) return closeDelete();
    if (event.target.closest("[data-instance-clear-runs]")) {
      if (!deleteTarget) return;
      clearButton.disabled = true; clearLabel.textContent = "Clearing…";
      try {
        const response = await fetch(`/admin/instances/${deleteTarget.id}/clear_test_runs`, { method:"POST", headers:{"X-CSRF-Token":getCsrfToken()} });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) return setTextError(deleteError, data.error || "Failed to clear test runs.");
        toast?.info(`Cleared ${data.cleared} test run(s).`);
        const usageResponse = await fetch(`/admin/instances/${deleteTarget.id}/usage`);
        if (usageResponse.ok) deleteUsage = await usageResponse.json();
        renderUsage();
      } finally { clearButton.disabled=false; clearLabel.textContent="Clear test run history"; }
      return;
    }
    if (event.target.closest("[data-instance-delete-confirm]")) {
      if (!deleteTarget || Number(deleteUsage?.test_runs || 0) > 0) return;
      deleteButton.disabled=true; deleteLabel.textContent="Deleting…"; setTextError(deleteError);
      try {
        const response=await fetch(`/admin/instances/${deleteTarget.id}`,{method:"DELETE",headers:{"X-CSRF-Token":getCsrfToken()}});
        const data=await response.json().catch(()=>({}));
        if(!response.ok)return setTextError(deleteError,data.error||"Delete failed.");
        location.reload();
      } finally { deleteButton.disabled=false; deleteLabel.textContent="Delete"; }
      return;
    }
    if (!event.target.closest("[data-instance-save]")) return;
    const form = Object.fromEntries(Object.entries(fields).map(([name, field]) => [name, field.value]));
    form.id = form.id.trim().toLowerCase().replace(/\s+/g, "_");
    if (!form.display_name.trim() || !form.image_tag.trim()) return setTextError(editError, "Display name and image tag are required.");
    saveButton.disabled=true; saveLabel.textContent="Saving…"; setTextError(editError);
    try {
      const response=await fetch(editingId?`/admin/instances/${editingId}`:"/admin/instances/",{method:editingId?"PUT":"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":getCsrfToken()},body:JSON.stringify(form)});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)return setTextError(editError,data.error||"Save failed.");
      location.reload();
    } finally { saveButton.disabled=false; saveLabel.textContent=editingId?"Save":"Register"; }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!editDialog.hidden) closeEdit();
    if (!deleteDialog.hidden) closeDelete();
  });
});
