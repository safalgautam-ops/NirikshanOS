// Runs immediately (not deferred) so the saved theme is applied before paint.
if (localStorage.theme === "light") {
  document.documentElement.classList.remove("dark");
}

// Wires up the theme-toggle button once the DOM is ready.
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("theme-toggle");
  if (!toggle) return;

  toggle.addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    localStorage.theme = document.documentElement.classList.contains("dark")
      ? "dark"
      : "light";
  });
});
