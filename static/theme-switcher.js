(function () {
  const STORAGE_KEY = "workspace-theme";
  const DEFAULT_THEME = "cloud-blue";

  function safeReadTheme() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
    } catch (error) {
      return DEFAULT_THEME;
    }
  }

  function safeSaveTheme(theme) {
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
      return;
    }
  }

  function closePanel(root, panel, toggle) {
    if (!(root instanceof HTMLElement) || !(panel instanceof HTMLElement) || !(toggle instanceof HTMLButtonElement)) {
      return;
    }

    root.classList.remove("is-open");
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  function openPanel(root, panel, toggle) {
    if (!(root instanceof HTMLElement) || !(panel instanceof HTMLElement) || !(toggle instanceof HTMLButtonElement)) {
      return;
    }

    root.classList.add("is-open");
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
  }

  window.addEventListener("DOMContentLoaded", function () {
    const root = document.querySelector("[data-theme-switcher]");
    const panel = document.querySelector("[data-theme-panel]");
    const toggle = document.querySelector("[data-theme-toggle]");
    const close = document.querySelector("[data-theme-close]");
    const cards = Array.from(document.querySelectorAll("[data-theme-option]"));
    const labelNode = document.querySelector("[data-theme-current-label]");
    const captionNode = document.querySelector("[data-theme-current-caption]");

    if (
      !(root instanceof HTMLElement) ||
      !(panel instanceof HTMLElement) ||
      !(toggle instanceof HTMLButtonElement) ||
      !cards.length
    ) {
      return;
    }

    function resolveTheme(theme) {
      const match = cards.find(function (card) {
        return card.getAttribute("data-theme-option") === theme;
      });
      return match ? theme : DEFAULT_THEME;
    }

    function applyTheme(theme, persist) {
      const resolvedTheme = resolveTheme(theme);
      document.documentElement.setAttribute("data-theme", resolvedTheme);
      if (persist) {
        safeSaveTheme(resolvedTheme);
      }

      let activeCard = null;
      cards.forEach(function (card) {
        const isActive = card.getAttribute("data-theme-option") === resolvedTheme;
        card.classList.toggle("is-active", isActive);
        card.setAttribute("aria-pressed", isActive ? "true" : "false");
        if (isActive) {
          activeCard = card;
        }
      });

      if (activeCard instanceof HTMLElement) {
        if (labelNode instanceof HTMLElement) {
          labelNode.textContent = activeCard.getAttribute("data-theme-label") || "云岸淡蓝";
        }
        if (captionNode instanceof HTMLElement) {
          captionNode.textContent = activeCard.getAttribute("data-theme-caption") || "";
        }
      }
    }

    applyTheme(safeReadTheme(), false);

    toggle.addEventListener("click", function () {
      if (panel.hidden) {
        openPanel(root, panel, toggle);
      } else {
        closePanel(root, panel, toggle);
      }
    });

    if (close instanceof HTMLButtonElement) {
      close.addEventListener("click", function () {
        closePanel(root, panel, toggle);
      });
    }

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        const theme = card.getAttribute("data-theme-option") || DEFAULT_THEME;
        applyTheme(theme, true);
        closePanel(root, panel, toggle);
      });
    });

    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (!root.contains(target)) {
        closePanel(root, panel, toggle);
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closePanel(root, panel, toggle);
      }
    });
  });
})();
