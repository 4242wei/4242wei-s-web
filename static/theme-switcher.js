(function () {
  const STORAGE_KEY = "workspace-theme";
  const MOTION_STORAGE_KEY = "workspace-theme-motion";
  const DEFAULT_THEME = "seaside-blue-hour";
  const RETIRED_THEMES = {
    "harbor-mist": "sky-confetti",
    "verdigris-studio": "citrus-bloom",
    "midnight-ember": "aurora-glass",
    "spring-moss": "cherry-picnic",
    "plum-rain": "lavender-soda",
    "jiangnan-drizzle": "tidal-spark",
    "westlake-spring": "westlake-snow",
    "westlake-summer": "westlake-snow",
    "westlake-autumn": "westlake-snow",
    "westlake-winter": "westlake-snow",
  };

  function safeReadTheme() {
    try {
      const storedTheme = window.localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
      const resolvedTheme = RETIRED_THEMES[storedTheme] || storedTheme;
      if (resolvedTheme !== storedTheme) {
        window.localStorage.setItem(STORAGE_KEY, resolvedTheme);
      }
      return resolvedTheme;
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

  function safeReadMotion() {
    try {
      return window.localStorage.getItem(MOTION_STORAGE_KEY) === "off" ? "off" : "on";
    } catch (error) {
      return "on";
    }
  }

  function safeSaveMotion(motion) {
    try {
      window.localStorage.setItem(MOTION_STORAGE_KEY, motion);
    } catch (error) {
      return;
    }
  }

  function ensureCloudStage() {
    const existingStage = document.querySelector("[data-theme-cloud-stage]");
    if (existingStage instanceof HTMLElement) {
      return existingStage;
    }

    const stage = document.createElement("div");
    stage.className = "theme-cloud-stage";
    stage.setAttribute("data-theme-cloud-stage", "");
    stage.setAttribute("aria-hidden", "true");

    ["a", "b", "c", "d", "e"].forEach(function (layerName) {
      const cloud = document.createElement("span");
      cloud.className = "theme-cloud theme-cloud--" + layerName;
      stage.appendChild(cloud);
    });

    ["a", "b", "c"].forEach(function (coreName) {
      const core = document.createElement("span");
      core.className = "theme-cloud-core theme-cloud-core--" + coreName;
      stage.appendChild(core);
    });

    document.body.insertBefore(stage, document.body.firstChild);
    return stage;
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
    ensureCloudStage();
    const root = document.querySelector("[data-theme-switcher]");
    const panel = document.querySelector("[data-theme-panel]");
    const toggle = document.querySelector("[data-theme-toggle]");
    const close = document.querySelector("[data-theme-close]");
    const motionToggle = document.querySelector("[data-theme-motion-toggle]");
    const motionState = document.querySelector("[data-theme-motion-state]");
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
          labelNode.textContent = activeCard.getAttribute("data-theme-label") || "海风蓝调";
        }
        if (captionNode instanceof HTMLElement) {
          captionNode.textContent = activeCard.getAttribute("data-theme-caption") || "";
        }
      }
    }

    function applyMotion(motion, persist) {
      const resolvedMotion = motion === "off" ? "off" : "on";
      const isEnabled = resolvedMotion === "on";
      document.documentElement.setAttribute("data-theme-motion", resolvedMotion);
      if (persist) {
        safeSaveMotion(resolvedMotion);
      }
      if (motionToggle instanceof HTMLButtonElement) {
        motionToggle.classList.toggle("is-enabled", isEnabled);
        motionToggle.setAttribute("aria-pressed", isEnabled ? "true" : "false");
      }
      if (motionState instanceof HTMLElement) {
        motionState.textContent = isEnabled ? "开" : "关";
      }
    }

    applyTheme(safeReadTheme(), false);
    applyMotion(safeReadMotion(), false);

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

    if (motionToggle instanceof HTMLButtonElement) {
      motionToggle.addEventListener("click", function () {
        const currentMotion = document.documentElement.getAttribute("data-theme-motion") || "on";
        applyMotion(currentMotion === "on" ? "off" : "on", true);
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
