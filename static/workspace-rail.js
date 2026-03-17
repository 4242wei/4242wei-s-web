(function () {
  const RAIL_STATE_KEY = "workspace-rail-collapsed";

  function readRailPreference() {
    try {
      return window.localStorage.getItem(RAIL_STATE_KEY) === "true";
    } catch (error) {
      return false;
    }
  }

  function writeRailPreference(collapsed) {
    try {
      window.localStorage.setItem(RAIL_STATE_KEY, collapsed ? "true" : "false");
    } catch (error) {
      return;
    }
  }

  function applyRailState(pageShell, toggle, collapsed) {
    pageShell.classList.toggle("is-rail-collapsed", collapsed);

    if (!(toggle instanceof HTMLButtonElement)) {
      return;
    }

    const expanded = !collapsed;
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggle.setAttribute("aria-label", expanded ? "折叠功能区" : "展开功能区");
    toggle.setAttribute("title", expanded ? "折叠功能区" : "展开功能区");
  }

  function setupWorkspaceRail() {
    const pageShell = document.querySelector(".page-shell");
    const toggle = document.querySelector("[data-workspace-rail-toggle]");
    if (!(pageShell instanceof HTMLElement) || !(toggle instanceof HTMLButtonElement)) {
      return;
    }

    applyRailState(pageShell, toggle, readRailPreference());

    toggle.addEventListener("click", function () {
      const collapsed = !pageShell.classList.contains("is-rail-collapsed");
      applyRailState(pageShell, toggle, collapsed);
      writeRailPreference(collapsed);
    });
  }

  window.addEventListener("DOMContentLoaded", setupWorkspaceRail);
})();
