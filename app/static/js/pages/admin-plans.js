(() => {
  const root = document.querySelector('[data-plans-page]');
  const dialog = document.querySelector('[data-plan-dialog]');
  const form = document.getElementById('plan-form');
  if (!root || !dialog || !form) return;

  let plans = [];
  try { plans = JSON.parse(document.getElementById('plans-data')?.textContent || '[]'); } catch { plans = []; }
  const byId = new Map(plans.map((plan) => [String(plan.id), plan]));
  let editId = null;
  const csrf = window.getCsrfToken();
  const $ = (id) => document.getElementById(id);

  function setValue(id, value) { const node = $(id); if (node) node.value = value ?? ''; }
  function setChecked(selector, values) {
    const selected = new Set((values || []).map(String));
    document.querySelectorAll(selector).forEach((node) => { node.checked = selected.has(String(node.value)); });
  }
  function switchTab(name) {
    document.querySelectorAll('[data-plan-panel]').forEach((panel) => { panel.hidden = panel.dataset.planPanel !== name; });
    document.querySelectorAll('[data-plan-tab]').forEach((button) => {
      const active = button.dataset.planTab === name;
      button.classList.toggle('border-primary', active);
      button.classList.toggle('border-transparent', !active);
      button.classList.toggle('text-muted-foreground', !active);
    });
  }
  function open(plan) {
    editId = plan ? String(plan.id) : null;
    $('plan-dialog-title').textContent = plan ? 'Edit Plan' : 'New Plan';
    $('plan-dialog-description').textContent = plan ? 'Changes take effect immediately. Existing subscribers keep their snapshot.' : 'Set up a new subscription tier.';
    $('plan-submit').textContent = plan ? 'Save Changes' : 'Create Plan';
    $('plan-id-field').hidden = !!plan;
    $('plan-id').disabled = !!plan;
    setValue('plan-id', plan?.id || '');
    setValue('plan-name', plan?.display_name || '');
    setValue('plan-sort', plan?.sort_order || 0);
    setValue('plan-description', plan?.description || '');
    setValue('plan-monthly', Number(plan?.price_monthly || 0));
    setValue('plan-annual', Number(plan?.price_annual || 0));
    setValue('plan-ram', plan?.resources?.ram_gb || 2);
    setValue('plan-vcpu', plan?.resources?.vcpu || 2);
    setValue('plan-storage', plan?.resources?.storage_gb || 20);
    $('plan-active').checked = plan?.is_active === undefined ? true : !!plan.is_active;
    setChecked('[data-plan-tier]', plan?.allowed_tiers || ['basic']);
    setChecked('[data-plan-instance]', plan?.allowed_instance_ids || []);
    $('plan-error').hidden = true;
    switchTab('general');
    window.openAppDialog(dialog);
  }
  function close() { window.closeAppDialog(dialog); }

  document.addEventListener('click', async (event) => {
    const create = event.target.closest('[data-plan-create]');
    if (create) { open(null); return; }
    const edit = event.target.closest('[data-plan-edit]');
    if (edit) { open(byId.get(edit.dataset.planEdit)); return; }
    const closeButton = event.target.closest('[data-plan-close]');
    if (closeButton) { close(); return; }
    const tab = event.target.closest('[data-plan-tab]');
    if (tab) { switchTab(tab.dataset.planTab); return; }
    const remove = event.target.closest('[data-plan-delete]');
    if (!remove) return;
    const plan = byId.get(remove.dataset.planDelete);
    if (!plan || !confirm(`Delete "${plan.display_name}"? Existing subscribers will be grandfathered until expiry.`)) return;
    const response = await fetch(`/admin/plans/${plan.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrf } });
    if (response.ok) location.reload();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = $('plan-submit');
    const error = $('plan-error');
    submit.disabled = true;
    submit.textContent = 'Saving…';
    error.hidden = true;
    const data = new FormData(form);
    try {
      let response;
      if (editId) {
        const payload = {
          display_name: data.get('display_name'), description: data.get('description'),
          price_monthly: Number(data.get('price_monthly')), price_annual: Number(data.get('price_annual')),
          ram_gb: Number(data.get('ram_gb')), vcpu: Number(data.get('vcpu')), storage_gb: Number(data.get('storage_gb')),
          allowed_tiers: data.getAll('allowed_tiers'), allowed_instance_ids: data.getAll('allowed_instance_ids'),
          is_active: data.get('is_active') === 'on', sort_order: Number(data.get('sort_order') || 0),
        };
        response = await fetch(`/admin/plans/${editId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(payload) });
      } else {
        response = await fetch('/admin/plans/', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: data });
      }
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        error.textContent = body.error || (editId ? 'Save failed.' : 'Create failed. Check that the Plan ID is unique.');
        error.hidden = false;
        return;
      }
      location.reload();
    } finally {
      submit.disabled = false;
      submit.textContent = editId ? 'Save Changes' : 'Create Plan';
    }
  });
})();
