(function () {
  const STORAGE_KEY = "portfolio-nav-layout";

  function applyLayout(mode) {
    const root = document.documentElement;
    const isTop = mode === "top";
    root.classList.toggle("nav-layout-top", isTop);
    root.classList.toggle("nav-layout-sidebar", !isTop);
    document.querySelectorAll("[data-layout-value]").forEach((button) => {
      const selected = button.dataset.layoutValue === mode;
      button.classList.toggle("is-active", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
  }

  function readLayout() {
    return localStorage.getItem(STORAGE_KEY) === "top" ? "top" : "sidebar";
  }

  window.applyNavLayout = applyLayout;

  document.addEventListener("DOMContentLoaded", () => {
    applyLayout(readLayout());

    document.body.addEventListener("click", (event) => {
      const button = event.target.closest("[data-layout-value]");
      if (!button) {
        return;
      }
      const mode = button.dataset.layoutValue === "top" ? "top" : "sidebar";
      localStorage.setItem(STORAGE_KEY, mode);
      applyLayout(mode);
    });
  });
})();
