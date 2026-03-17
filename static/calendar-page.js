(function () {
  const root = document.querySelector("[data-calendar-page-root]");
  if (!root) {
    return;
  }

  let requestController = null;

  function getParts() {
    return {
      hero: root.querySelector("[data-calendar-page-hero]"),
      main: root.querySelector("[data-calendar-page-main]"),
    };
  }

  function setBusy(isBusy) {
    const parts = getParts();
    [parts.hero, parts.main].forEach(function (element) {
      if (!(element instanceof HTMLElement)) {
        return;
      }
      element.classList.toggle("is-loading", isBusy);
      element.setAttribute("aria-busy", isBusy ? "true" : "false");
    });
  }

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

  async function replaceCalendarPage(url, historyMode) {
    const normalizedUrl = new URL(url, window.location.origin);
    normalizedUrl.hash = "";
    const targetUrl = `${normalizedUrl.pathname}${normalizedUrl.search}`;
    const currentScrollY = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;

    if (requestController) {
      requestController.abort();
    }

    requestController = new AbortController();
    setBusy(true);

    try {
      const response = await fetch(targetUrl, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        signal: requestController.signal,
      });

      if (!response.ok) {
        throw new Error("calendar-page-fetch-failed");
      }

      const html = await response.text();
      const parser = new DOMParser();
      const nextDocument = parser.parseFromString(html, "text/html");
      const nextRoot = nextDocument.querySelector("[data-calendar-page-root]");
      const nextHero = nextRoot?.querySelector("[data-calendar-page-hero]");
      const nextMain = nextRoot?.querySelector("[data-calendar-page-main]");
      const parts = getParts();

      if (!(parts.hero instanceof HTMLElement) || !(parts.main instanceof HTMLElement) || !(nextHero instanceof HTMLElement) || !(nextMain instanceof HTMLElement)) {
        window.location.assign(url);
        return;
      }

      parts.hero.replaceWith(nextHero);
      parts.main.replaceWith(nextMain);
      document.title = nextDocument.title || document.title;

      if (historyMode === "replace") {
        window.history.replaceState({}, "", targetUrl);
      } else if (historyMode === "push") {
        window.history.pushState({}, "", targetUrl);
      }

      const restoreScroll = function () {
        window.scrollTo({ top: currentScrollY, left: 0, behavior: "auto" });
      };

      restoreScroll();
      window.requestAnimationFrame(restoreScroll);
      window.setTimeout(restoreScroll, 60);
      window.setTimeout(restoreScroll, 180);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      window.location.assign(targetUrl);
    } finally {
      setBusy(false);
      requestController = null;
    }
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const link = target.closest("a[data-calendar-page-link]");
    if (!(link instanceof HTMLAnchorElement)) {
      return;
    }

    event.preventDefault();
    replaceCalendarPage(link.href, "push");
  });

  document.addEventListener("change", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    const form = target.closest("form[data-calendar-page-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    replaceCalendarPage(buildUrlFromForm(form), "push");
  });

  document.addEventListener("submit", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLFormElement) || !target.matches("form[data-calendar-page-form]")) {
      return;
    }

    event.preventDefault();
    replaceCalendarPage(buildUrlFromForm(target), "push");
  });

  window.addEventListener("popstate", function () {
    replaceCalendarPage(window.location.href, "replace");
  });
})();
