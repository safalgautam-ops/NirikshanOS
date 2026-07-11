// Page-specific JS for cases/list.html — the case create dialog's member picker.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("caseCreateForm", (orgMembers) => ({
    query: "",
    open: false,
    members: [],
    allMembers: orgMembers || [],

    filtered() {
      const q = this.query.trim().toLowerCase();
      const chosenIds = new Set(this.members.map((m) => m.id));
      return this.allMembers
        .filter((m) => !chosenIds.has(m.id))
        .filter((m) => !q || m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q))
        .slice(0, 8);
    },

    addMember(member) {
      if (this.members.some((existing) => existing.id === member.id)) return;
      this.members.push(member);
      this.query = "";
      this.open = false;
    },

    removeMember(id) {
      this.members = this.members.filter((m) => m.id !== id);
    },
  }));
});
