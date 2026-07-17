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

(() => {
  initListFilter();
  const root = document.querySelector('[data-timeline-page]');
  if (!root) return;

  const dataNode = document.getElementById('timeline-items-data');
  let items = {};
  try { items = JSON.parse(dataNode?.textContent || '{}'); } catch { items = {}; }

  const caseId = root.dataset.caseId;
  const dialog = document.getElementById('edit-timeline-item-dialog');
  const form = document.getElementById('edit-timeline-form');
  const title = document.getElementById('edit-timeline-title');
  const commonTitle = document.getElementById('edit-timeline-item-title');
  const description = document.getElementById('edit-timeline-item-description');
  const typePanels = [...document.querySelectorAll('[data-edit-type]')];

  const field = (id) => document.getElementById(id);
  const set = (id, value) => { const node = field(id); if (node) node.value = value ?? ''; };

  function enablePanel(panel, enabled) {
    panel.hidden = !enabled;
    panel.querySelectorAll('input, select, textarea').forEach((control) => { control.disabled = !enabled; });
  }

  function openItem(itemId) {
    const item = items[itemId];
    if (!item || !dialog || !form) return;
    const label = item.type === 'task' ? 'Task' : item.type === 'note' ? 'Note' : 'Milestone';
    title.textContent = `Edit ${label}`;
    form.action = `/cases/${caseId}/timeline/items/${item.id}/edit`;
    commonTitle.value = item.title || '';
    description.value = item.description || '';
    typePanels.forEach((panel) => enablePanel(panel, panel.dataset.editType === item.type));

    if (item.type === 'task') {
      set('edit-task-status', item.status);
      set('edit-task-priority', item.priority);
      set('edit-task-assigned', item.assigned_to);
      set('edit-task-due-date', item.due_date);
      set('edit-task-time', item.timeline_time);
      set('edit-task-evidence', item.linked_evidence_id);
      set('edit-task-result', item.linked_result_label);
    } else if (item.type === 'note') {
      set('edit-note-time', item.timeline_time);
      set('edit-note-visibility', item.visibility);
    } else {
      set('edit-milestone-time', item.timeline_time);
    }
    window.openAppDialog(dialog);
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-edit-timeline-item]');
    if (!trigger) return;
    event.preventDefault();
    openItem(trigger.dataset.editTimelineItem);
  });
})();
