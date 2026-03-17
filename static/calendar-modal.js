(function () {
  const overlay = document.querySelector("[data-calendar-overlay]");
  const content = document.querySelector("[data-calendar-content]");
  const launchers = document.querySelectorAll("[data-calendar-launch]");

  if (!overlay || !content || !launchers.length) {
    return;
  }

  let activeUrl = "";

  function buildUrlFromForm(form) {
    const action = form.getAttribute("action") || window.location.pathname;
    const url = new URL(action, window.location.origin);
    const formData = new FormData(form);

    for (const [key, value] of formData.entries()) {
      if (typeof value === "string" && value) {
        url.searchParams.set(key, value);
      }
    }

    return `${url.pathname}?${url.searchParams.toString()}`;
  }

  function normalizeUrl(url) {
    const parsed = new URL(url, window.location.origin);
    parsed.hash = "";
    return `${parsed.pathname}${parsed.search}`;
  }

  function monthKeyFromUrl(url) {
    const parsed = new URL(url, window.location.origin);
    const month = parsed.searchParams.get("month");
    if (month) {
      return month;
    }

    const year = parsed.searchParams.get("year");
    const monthNumber = parsed.searchParams.get("month_number");
    if (year && monthNumber) {
      return `${year}-${String(monthNumber).padStart(2, "0")}`;
    }

    return "";
  }

  function activeModalRoot() {
    return content.querySelector("[data-calendar-modal-root]");
  }

  function activeMonthKey() {
    return activeModalRoot()?.getAttribute("data-calendar-month-key") || "";
  }

  function lockBody(isLocked) {
    document.body.style.overflow = isLocked ? "hidden" : "";
  }

  function openOverlay() {
    overlay.hidden = false;
    overlay.classList.add("is-open");
    lockBody(true);
  }

  function closeOverlay() {
    overlay.classList.remove("is-open");
    overlay.hidden = true;
    content.innerHTML = "";
    lockBody(false);
  }

  function renderLoadError() {
    content.innerHTML = '<div class="calendar-modal-loading">当前无法加载日历，请稍后再试。</div>';
  }

  async function fetchFragment(url) {
    const response = await fetch(normalizeUrl(url), {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });

    if (!response.ok) {
      throw new Error("calendar-fragment-failed");
    }

    return response.text();
  }

  async function loadFragment(url) {
    activeUrl = normalizeUrl(url);
    content.innerHTML = '<div class="calendar-modal-loading">正在加载日历...</div>';
    openOverlay();
    content.innerHTML = await fetchFragment(url);
  }

  async function updateSideOnly(url) {
    const html = await fetchFragment(url);
    const parser = new DOMParser();
    const nextDocument = parser.parseFromString(html, "text/html");
    const nextRoot = nextDocument.querySelector("[data-calendar-modal-root]");
    const nextSide = nextRoot?.querySelector("[data-calendar-modal-side]");
    const nextGrid = nextRoot?.querySelector("[data-calendar-modal-grid]");
    const currentRoot = activeModalRoot();
    const currentSide = currentRoot?.querySelector("[data-calendar-modal-side]");
    const currentGrid = currentRoot?.querySelector("[data-calendar-modal-grid]");

    if (
      !(nextSide instanceof HTMLElement) ||
      !(currentSide instanceof HTMLElement) ||
      !(currentRoot instanceof HTMLElement) ||
      !(nextGrid instanceof HTMLElement) ||
      !(currentGrid instanceof HTMLElement)
    ) {
      await loadFragment(url);
      return;
    }

    currentSide.replaceWith(nextSide);
    currentRoot.setAttribute("data-calendar-month-key", nextRoot.getAttribute("data-calendar-month-key") || "");
    activeUrl = normalizeUrl(url);

    const nextClasses = new Map();
    nextGrid.querySelectorAll("[data-calendar-date]").forEach(function (element) {
      if (!(element instanceof HTMLElement)) {
        return;
      }
      nextClasses.set(element.getAttribute("data-calendar-date") || "", element.className);
    });

    currentGrid.querySelectorAll("[data-calendar-date]").forEach(function (element) {
      if (!(element instanceof HTMLElement)) {
        return;
      }
      const date = element.getAttribute("data-calendar-date") || "";
      element.className = nextClasses.get(date) || element.className;
    });
  }

  function shouldUseSideOnlyUpdate(link) {
    if (!(link instanceof HTMLAnchorElement) || !link.hasAttribute("data-calendar-date")) {
      return false;
    }

    const targetMonth = monthKeyFromUrl(link.href);
    const currentMonth = activeMonthKey();
    return Boolean(targetMonth && currentMonth && targetMonth === currentMonth);
  }

  launchers.forEach(function (launcher) {
    launcher.addEventListener("click", function (event) {
      event.preventDefault();
      const url = launcher.getAttribute("data-calendar-url") || launcher.getAttribute("href");
      if (!url) {
        return;
      }

      loadFragment(url).catch(renderLoadError);
    });
  });

  overlay.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.closest("[data-calendar-close]")) {
      closeOverlay();
      return;
    }

    const link = target.closest("[data-calendar-fragment-link]");
    if (link instanceof HTMLAnchorElement) {
      event.preventDefault();
      if (shouldUseSideOnlyUpdate(link)) {
        updateSideOnly(link.href).catch(renderLoadError);
      } else {
        loadFragment(link.href).catch(renderLoadError);
      }
      return;
    }

    if (target.hasAttribute("data-calendar-overlay") || target.hasAttribute("data-calendar-close")) {
      closeOverlay();
    }
  });

  overlay.addEventListener("change", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const form = target.closest("form[data-calendar-fragment-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    loadFragment(buildUrlFromForm(form)).catch(renderLoadError);
  });

  overlay.addEventListener("submit", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLFormElement) || !target.matches("form[data-calendar-fragment-form]")) {
      return;
    }

    event.preventDefault();
    loadFragment(buildUrlFromForm(target)).catch(renderLoadError);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) {
      closeOverlay();
    }
  });

  overlay.querySelector("[data-calendar-close]")?.addEventListener("click", closeOverlay);

  window.addEventListener("beforeunload", function () {
    if (activeUrl) {
      lockBody(false);
    }
  });
})();
