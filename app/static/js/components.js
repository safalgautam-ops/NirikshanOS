// Small Alpine.data() components that need real JS (DOM measurement, multi-
// statement logic) the CSP build's inline-attribute parser can't run - see
// the comment in layouts/base.html on why that parser only handles simple
// expressions. Lives in a real same-origin file, so CSP (script-src 'self')
// allows it; this is the supported way to do anything non-trivial with the
// CSP build, not a workaround.
document.addEventListener("alpine:init", () => {
  // Drives tabs.html's sliding active-tab indicator (next-app's TabsList).
  // Measures the active trigger's box and writes it as inline style on the
  // indicator element so it can be a plain absolutely-positioned div.
  Alpine.data("tabsIndicator", (initialTab) => ({
    tab: initialTab,
    indicatorStyle: "",

    init() {
      this.moveIndicator();
      window.addEventListener("resize", () => this.moveIndicator());
    },

    selectTab(value) {
      this.tab = value;
      this.$nextTick(() => this.moveIndicator());
    },

    moveIndicator() {
      const active = this.$refs.list.querySelector('[data-active="true"]');
      if (!active) {
        this.indicatorStyle = "";
        return;
      }
      this.indicatorStyle =
        "width:" + active.offsetWidth + "px;" +
        "height:" + active.offsetHeight + "px;" +
        "transform:translateX(" + active.offsetLeft + "px)";
    },
  }));
});
