(function () {
  const KEY_PREFIX = "stock-detail-active-panel:";

  function getStorageKey() {
    return `${KEY_PREFIX}${window.location.pathname}`;
  }

  function resolvePanelFromHash(panels) {
    if (window.location.hash) {
      const hash = window.location.hash.slice(1);
      const matchedPanel = panels.find(function (panel) {
        return panel.id === hash;
      });
      if (matchedPanel && matchedPanel.dataset.stockDetailPanel) {
        return matchedPanel.dataset.stockDetailPanel;
      }

      const targetElement = document.getElementById(hash);
      if (targetElement instanceof HTMLElement) {
        const parentPanel = targetElement.closest("[data-stock-detail-panel]");
        if (parentPanel instanceof HTMLElement && parentPanel.dataset.stockDetailPanel) {
          return parentPanel.dataset.stockDetailPanel;
        }
      }
    }

    return "";
  }

  function findInitialPanel(buttons, panels) {
    const validPanels = new Set(
      panels
        .map(function (panel) {
          return panel.dataset.stockDetailPanel;
        })
        .filter(Boolean)
    );

    const hashPanel = resolvePanelFromHash(panels);
    if (hashPanel) {
      return hashPanel;
    }

    const stored = sessionStorage.getItem(getStorageKey());
    if (stored && validPanels.has(stored)) {
      return stored;
    }

    const defaultButton =
      buttons.find(function (button) {
        return button.hasAttribute("data-stock-detail-default");
      }) || buttons[0];

    return defaultButton ? defaultButton.dataset.stockDetailPanelTarget : "";
  }

  function setActivePanel(panelName, buttons, panels) {
    if (!panelName) {
      return;
    }

    buttons.forEach(function (button) {
      const isActive = button.dataset.stockDetailPanelTarget === panelName;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", isActive ? "true" : "false");
      button.tabIndex = isActive ? 0 : -1;
    });

    panels.forEach(function (panel) {
      const isActive = panel.dataset.stockDetailPanel === panelName;
      panel.hidden = !isActive;
      panel.classList.toggle("is-active", isActive);
    });

    sessionStorage.setItem(getStorageKey(), panelName);
  }

  window.addEventListener("DOMContentLoaded", function () {
    const buttons = Array.from(document.querySelectorAll("[data-stock-detail-panel-target]"));
    const panels = Array.from(document.querySelectorAll("[data-stock-detail-panel]"));

    if (!buttons.length || !panels.length) {
      return;
    }

    setActivePanel(findInitialPanel(buttons, panels), buttons, panels);

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        setActivePanel(button.dataset.stockDetailPanelTarget, buttons, panels);
      });
    });

    window.addEventListener("hashchange", function () {
      const hashPanel = resolvePanelFromHash(panels);
      if (hashPanel) {
        setActivePanel(hashPanel, buttons, panels);
      }
    });
  });
})();
