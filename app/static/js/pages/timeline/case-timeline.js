// Page-specific JS for timeline/case_timeline.html — the edit-item dialog.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("timelinePage", (itemsById, caseId) => ({
    itemsById: itemsById || {},
    caseId,
    editingItem: null,

    openEditDialog(itemId) {
      const item = this.itemsById[itemId];
      if (!item) return;
      this.editingItem = { ...item };
      const dialog = document.getElementById("edit-timeline-item-dialog");
      if (dialog) { dialog.dataset.state = "open"; if (!dialog.open) dialog.showModal(); }
    },

    editFormAction() {
      if (!this.editingItem) return "#";
      return "/cases/" + this.caseId + "/timeline/items/" + this.editingItem.id + "/edit";
    },
  }));
});
