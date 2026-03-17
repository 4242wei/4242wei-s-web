(function () {
  const SCROLL_KEY = "stock-page-scroll-context";

  function collectOpenDetails() {
    return Array.from(document.querySelectorAll("details[data-preserve-open-state][id][open]"))
      .map(function (item) {
        return item.id;
      })
      .filter(Boolean);
  }

  function collectShellScrolls() {
    const positions = {};

    document.querySelectorAll("[data-preserve-scroll-shell][id]").forEach(function (element) {
      if (!(element instanceof HTMLElement)) {
        return;
      }

      positions[element.id] = element.scrollTop;
    });

    return positions;
  }

  function rememberContext() {
    const payload = {
      path: window.location.pathname,
      scrollY: window.scrollY,
      openDetails: collectOpenDetails(),
      shellScrolls: collectShellScrolls(),
    };

    sessionStorage.setItem(SCROLL_KEY, JSON.stringify(payload));
  }

  function readContext() {
    const raw = sessionStorage.getItem(SCROLL_KEY);
    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  function restoreScrollY(savedY) {
    const top = Number.parseInt(savedY, 10);
    if (Number.isNaN(top)) {
      return false;
    }

    window.scrollTo(0, top);
    return true;
  }

  function restoreOpenDetails(savedIds) {
    if (!Array.isArray(savedIds) || !savedIds.length) {
      return;
    }

    savedIds.forEach(function (id) {
      const element = document.getElementById(id);
      if (element instanceof HTMLDetailsElement) {
        element.open = true;
      }
    });
  }

  function restoreShellScrolls(savedPositions) {
    if (!savedPositions || typeof savedPositions !== "object") {
      return;
    }

    Object.entries(savedPositions).forEach(function (entry) {
      const id = entry[0];
      const top = Number.parseInt(entry[1], 10);
      const element = document.getElementById(id);
      if (!(element instanceof HTMLElement) || Number.isNaN(top)) {
        return;
      }

      element.scrollTop = top;
    });
  }

  function restoreContext() {
    const params = new URLSearchParams(window.location.search);
    const focusGroup = params.get("focus_group");
    const saved = readContext();
    const hash = decodeURIComponent(window.location.hash || "");
    const root = document.documentElement;
    const previousBehavior = root.style.scrollBehavior;
    const originalRestoration = window.history.scrollRestoration;

    root.style.scrollBehavior = "auto";
    window.history.scrollRestoration = "manual";

    if (saved && saved.path === window.location.pathname) {
      restoreOpenDetails(saved.openDetails);
      restoreShellScrolls(saved.shellScrolls);
    }

    if (focusGroup && window.location.pathname === "/stocks") {
      const focusElement = document.getElementById(`group-${focusGroup}`) || document.getElementById(focusGroup);
      if (focusElement) {
        if (focusElement instanceof HTMLDetailsElement) {
          focusElement.open = true;
        }
        focusElement.scrollIntoView({ block: "start" });
      }

      params.delete("focus_group");
      const query = params.toString();
      const cleanUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
      window.history.replaceState({}, "", cleanUrl);
    } else if (hash) {
      const applyHashFocus = function () {
        restoreOpenDetails(saved?.openDetails);
        restoreShellScrolls(saved?.shellScrolls);
        const targetId = hash.replace(/^#/, "");
        const target = targetId ? document.getElementById(targetId) : null;
        if (target instanceof HTMLElement) {
          target.scrollIntoView({ block: "start" });
        }
      };

      applyHashFocus();
      window.requestAnimationFrame(applyHashFocus);
      window.setTimeout(applyHashFocus, 90);
      window.setTimeout(applyHashFocus, 240);
      window.addEventListener(
        "load",
        function () {
          applyHashFocus();
          window.setTimeout(applyHashFocus, 120);
        },
        { once: true }
      );
    } else if (saved && saved.path === window.location.pathname) {
      const applyRestore = function () {
        restoreOpenDetails(saved.openDetails);
        restoreShellScrolls(saved.shellScrolls);
        restoreScrollY(saved.scrollY);
      };

      applyRestore();
      window.requestAnimationFrame(applyRestore);
      window.setTimeout(applyRestore, 90);
      window.setTimeout(applyRestore, 240);
      window.addEventListener(
        "load",
        function () {
          applyRestore();
          window.setTimeout(applyRestore, 120);
        },
        { once: true }
      );
    }

    sessionStorage.removeItem(SCROLL_KEY);

    window.requestAnimationFrame(function () {
      root.style.scrollBehavior = previousBehavior;
      window.history.scrollRestoration = originalRestoration;
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    const forms = document.querySelectorAll("form[data-preserve-scroll]");
    const links = document.querySelectorAll("a[data-preserve-scroll-link]");
    const autoSubmitForms = document.querySelectorAll("form[data-auto-submit]");

    restoreContext();

    forms.forEach(function (form) {
      form.addEventListener("submit", function () {
        rememberContext();
      });
    });

    links.forEach(function (link) {
      link.addEventListener("click", function () {
        rememberContext();
      });
    });

    autoSubmitForms.forEach(function (form) {
      const fields = form.querySelectorAll("select, input[type='month'], input[type='date']");
      fields.forEach(function (field) {
        field.addEventListener("change", function () {
          rememberContext();
          if (form instanceof HTMLFormElement) {
            form.requestSubmit();
          }
        });
      });
    });
  });
})();
