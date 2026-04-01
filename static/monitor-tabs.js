(function () {
  const TRANSITION_MS = 220;

  function normalizeTab(value) {
    const raw = String(value || "").trim().toLowerCase();
    return raw === "signals" ? "signals" : "info";
  }

  function buildNextUrl(tab) {
    const url = new URL(window.location.href);
    const normalizedTab = normalizeTab(tab);
    if (normalizedTab === "info") {
      url.searchParams.delete("tab");
    } else {
      url.searchParams.set("tab", normalizedTab);
    }
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function bindSwitcher(root) {
    const triggers = Array.from(root.querySelectorAll("[data-monitor-tab-trigger]"));
    const panels = Array.from(document.querySelectorAll("[data-monitor-tab-panel]"));
    const copies = Array.from(document.querySelectorAll("[data-monitor-tab-copy]"));

    if (!triggers.length || !panels.length) {
      return;
    }

    let activeTab = normalizeTab(root.getAttribute("data-active-tab") || "info");
    let hideTimer = 0;

    function syncTriggers() {
      triggers.forEach(function (trigger) {
        if (!(trigger instanceof HTMLButtonElement)) {
          return;
        }
        const tab = normalizeTab(trigger.getAttribute("data-monitor-tab-trigger"));
        const isActive = tab === activeTab;
        trigger.classList.toggle("is-active", isActive);
        trigger.setAttribute("aria-selected", isActive ? "true" : "false");
        trigger.tabIndex = isActive ? 0 : -1;
      });
    }

    function syncCopies() {
      copies.forEach(function (copy) {
        if (!(copy instanceof HTMLElement)) {
          return;
        }
        const tab = normalizeTab(copy.getAttribute("data-monitor-tab-copy"));
        const isActive = tab === activeTab;
        copy.classList.toggle("is-active", isActive);
        copy.hidden = !isActive;
      });
    }

    function showPanel(panel, isActive) {
      if (!(panel instanceof HTMLElement)) {
        return;
      }

      if (isActive) {
        panel.hidden = false;
        panel.classList.remove("is-hiding");
        window.requestAnimationFrame(function () {
          panel.classList.add("is-active");
        });
        return;
      }

      panel.classList.remove("is-active");
      panel.classList.add("is-hiding");
      if (hideTimer) {
        window.clearTimeout(hideTimer);
      }
      hideTimer = window.setTimeout(function () {
        if (!panel.classList.contains("is-active")) {
          panel.hidden = true;
          panel.classList.remove("is-hiding");
        }
        hideTimer = 0;
      }, TRANSITION_MS);
    }

    function syncPanels() {
      panels.forEach(function (panel) {
        if (!(panel instanceof HTMLElement)) {
          return;
        }
        const tab = normalizeTab(panel.getAttribute("data-monitor-tab-panel"));
        showPanel(panel, tab === activeTab);
      });
    }

    function activateTab(nextTab, options) {
      const settings = options && typeof options === "object" ? options : {};
      const normalizedTab = normalizeTab(nextTab);
      if (normalizedTab === activeTab) {
        return;
      }

      activeTab = normalizedTab;
      root.setAttribute("data-active-tab", activeTab);
      syncTriggers();
      syncCopies();
      syncPanels();

      if (settings.updateHistory !== false) {
        window.history.replaceState({}, "", buildNextUrl(activeTab));
      }
    }

    function moveFocus(step) {
      const currentIndex = triggers.findIndex(function (trigger) {
        return (
          trigger instanceof HTMLButtonElement &&
          normalizeTab(trigger.getAttribute("data-monitor-tab-trigger")) === activeTab
        );
      });
      if (currentIndex === -1) {
        return;
      }
      const nextIndex = (currentIndex + step + triggers.length) % triggers.length;
      const nextTrigger = triggers[nextIndex];
      if (nextTrigger instanceof HTMLButtonElement) {
        nextTrigger.focus();
        activateTab(nextTrigger.getAttribute("data-monitor-tab-trigger") || "info");
      }
    }

    root.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const trigger = target.closest("[data-monitor-tab-trigger]");
      if (!(trigger instanceof HTMLButtonElement)) {
        return;
      }
      activateTab(trigger.getAttribute("data-monitor-tab-trigger") || "info");
    });

    root.addEventListener("keydown", function (event) {
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        event.preventDefault();
        moveFocus(1);
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        event.preventDefault();
        moveFocus(-1);
      }
    });

    syncTriggers();
    syncCopies();
    syncPanels();
  }

  window.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-monitor-tabs]").forEach(function (root) {
      if (root instanceof HTMLElement) {
        bindSwitcher(root);
      }
    });
  });
})();
