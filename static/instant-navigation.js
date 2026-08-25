(function () {
  const LINK_SELECTOR = ".workspace-rail-link, .masthead-nav--fallback .masthead-link";
  const prefetchedUrls = new Set();

  function connectionAllowsPrefetch() {
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!connection) {
      return true;
    }
    return !connection.saveData && !/^(slow-)?2g$/i.test(connection.effectiveType || "");
  }

  function eligibleUrl(link) {
    if (!(link instanceof HTMLAnchorElement) || link.hasAttribute("download")) {
      return null;
    }

    let url;
    try {
      url = new URL(link.href, window.location.href);
    } catch (error) {
      return null;
    }

    if (url.origin !== window.location.origin || url.protocol !== window.location.protocol) {
      return null;
    }
    if (url.pathname === window.location.pathname && url.search === window.location.search) {
      return null;
    }
    url.hash = "";
    return url.href;
  }

  function prefetchWithLink(url) {
    if (!url || prefetchedUrls.has(url)) {
      return;
    }
    prefetchedUrls.add(url);
    const hint = document.createElement("link");
    hint.rel = "prefetch";
    hint.as = "document";
    hint.href = url;
    document.head.appendChild(hint);
  }

  function installSpeculationRules(urls) {
    if (!(window.HTMLScriptElement && typeof HTMLScriptElement.supports === "function")) {
      return false;
    }
    if (!HTMLScriptElement.supports("speculationrules")) {
      return false;
    }

    const rules = document.createElement("script");
    rules.type = "speculationrules";
    rules.textContent = JSON.stringify({
      prefetch: [{ source: "list", urls: urls, eagerness: "moderate" }],
    });
    document.head.appendChild(rules);
    return true;
  }

  function beginNavigation(link) {
    document.documentElement.classList.add("is-navigating");
    document.documentElement.setAttribute("aria-busy", "true");
    link.classList.add("is-loading");
  }

  function resetNavigationState() {
    document.documentElement.classList.remove("is-navigating");
    document.documentElement.removeAttribute("aria-busy");
    document.querySelectorAll(LINK_SELECTOR).forEach(function (link) {
      link.classList.remove("is-loading");
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    const links = Array.from(document.querySelectorAll(LINK_SELECTOR));
    if (!links.length) {
      return;
    }

    const urls = Array.from(new Set(links.map(eligibleUrl).filter(Boolean)));
    const canPrefetch = connectionAllowsPrefetch() && document.visibilityState !== "hidden";
    const usesSpeculationRules = canPrefetch && installSpeculationRules(urls);

    links.forEach(function (link) {
      if (canPrefetch && !usesSpeculationRules) {
        const warm = function () {
          prefetchWithLink(eligibleUrl(link));
        };
        link.addEventListener("pointerenter", warm, { once: true, passive: true });
        link.addEventListener("focus", warm, { once: true, passive: true });
        link.addEventListener("touchstart", warm, { once: true, passive: true });
      }

      link.addEventListener("click", function (event) {
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey ||
          link.target === "_blank"
        ) {
          return;
        }
        beginNavigation(link);
      });
    });
  });

  window.addEventListener("pageshow", resetNavigationState);
})();
