(function () {
  const CHART_MIN_WIDTH = 880;
  const CHART_HEIGHT = 468;
  const CHART_DEFAULT_VISIBLE_BARS = 15;
  const CHART_BAR_WIDTH = 44;
  const CHART_BAR_GAP = 18;
  const CDN_TREND_MIN_WIDTH = 620;
  const CDN_TREND_HEIGHT = 336;
  const CDN_TREND_POINT_GAP = 58;
  const CDN_TREND_DEFAULT_VISIBLE_POINTS = 10;
  const GPU_PRICE_MIN_WIDTH = 880;
  const GPU_PRICE_HEIGHT = 468;
  const GPU_PRICE_POINT_GAP = 74;
  const GPU_PRICE_DEFAULT_VISIBLE_POINTS = 15;
  const TREND_WINDOW_DEFAULT = "30d";
  const TREND_VIEW_DEFAULT = "raw";
  const TREND_WINDOW_DAY_MAP = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    all: 0,
  };
  const chartEntries = [];
  const cdnTrendEntries = [];
  const gpuPriceChartEntries = [];
  const trendControlState = {
    cdn: {
      window: TREND_WINDOW_DEFAULT,
      view: TREND_VIEW_DEFAULT,
    },
    applovin: {
      window: TREND_WINDOW_DEFAULT,
      view: TREND_VIEW_DEFAULT,
    },
  };
  let activeLegendSymbol = "";
  let activeCdnTrendProvider = "";
  let activeGpuPriceFamily = "";
  let activeApplovinPoller = null;
  let applovinRequestController = null;
  let applovinPageshowBound = false;
  let applovinHistoryBound = false;
  let cdnTrendWindowBound = false;
  let cdnTrendVisualsInitialized = false;
  let cdnTrendVisualSignature = "";
  let gpuPriceWindowBound = false;
  let gpuPriceVisualsInitialized = false;
  let gpuPriceVisualSignature = "";
  let applovinDonutsInitialized = false;
  let applovinDonutSignature = "";
  let stablecoinVisualsInitialized = false;
  let hideActiveChartTooltip = function () {};
  let hideActiveCdnTrendTooltip = function () {};
  let hideActiveGpuPriceTooltip = function () {};

  function ensureFlashStack() {
    let stack = document.querySelector(".flash-stack");
    if (stack instanceof HTMLElement) {
      return stack;
    }

    stack = document.createElement("div");
    stack.className = "flash-stack";
    stack.setAttribute("role", "status");
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
    return stack;
  }

  function showFlash(kind, message) {
    if (!message) {
      return;
    }

    const stack = ensureFlashStack();
    const node = document.createElement("div");
    node.className = `flash-message flash-${kind}`;
    node.setAttribute("data-flash-message", "");
    node.innerHTML = '<div class="flash-body"></div><button class="flash-close" type="button" aria-label="关闭提示">X</button>';

    const body = node.querySelector(".flash-body");
    const close = node.querySelector(".flash-close");
    if (body instanceof HTMLElement) {
      body.textContent = message;
    }
    if (close instanceof HTMLButtonElement) {
      close.addEventListener("click", function () {
        node.remove();
      });
    }

    stack.prepend(node);
    window.setTimeout(function () {
      node.remove();
    }, kind === "error" ? 6400 : 3600);
  }

  function updateNodes(selector, value) {
    document.querySelectorAll(selector).forEach(function (node) {
      if (node instanceof HTMLElement) {
        node.textContent = value;
      }
    });
  }

  function applyRuntimeState(payload) {
    if (!payload || !payload.runtime) {
      return;
    }

    const runtime = payload.runtime;
    const panel = document.querySelector("[data-stablecoin-status-panel]");
    const refreshButton = document.querySelector("[data-stablecoin-refresh-button]");

    updateNodes("[data-stablecoin-status-label]", runtime.status_label || "待刷新");
    updateNodes("[data-stablecoin-started-at]", runtime.started_at_label || "尚未刷新");
    updateNodes("[data-stablecoin-finished-at]", runtime.finished_at_label || "尚未刷新");
    updateNodes("[data-stablecoin-last-updated], [data-stablecoin-last-updated-side]", payload.updated_at_label || "尚未抓取");

    const messageNode = document.querySelector("[data-stablecoin-message]");
    if (messageNode instanceof HTMLElement) {
      const message = runtime.message || "";
      messageNode.textContent = message;
      messageNode.hidden = !message;
    }

    const errorNode = document.querySelector("[data-stablecoin-error]");
    if (errorNode instanceof HTMLElement) {
      const error = runtime.error || "";
      errorNode.textContent = error;
      errorNode.hidden = !error;
    }

    if (panel instanceof HTMLElement) {
      panel.setAttribute("data-stablecoin-running", runtime.is_running ? "true" : "false");
      panel.setAttribute("data-stablecoin-status", runtime.status || "idle");
    }

    if (refreshButton instanceof HTMLButtonElement) {
      refreshButton.disabled = runtime.is_running;
      refreshButton.textContent = runtime.is_running ? "更新中" : "立即更新";
    }
  }

  function setupStatusPolling() {
    const panel = document.querySelector("[data-stablecoin-status-panel]");
    if (!(panel instanceof HTMLElement)) {
      return {
        start: function () {},
      };
    }

    const statusUrl = panel.getAttribute("data-status-url") || "";
    const pollSeconds = Number.parseInt(panel.getAttribute("data-stablecoin-poll-seconds") || "5", 10);
    let previousStatus = panel.getAttribute("data-stablecoin-status") || "idle";
    let timerId = 0;

    function stop() {
      if (!timerId) {
        return;
      }
      window.clearInterval(timerId);
      timerId = 0;
    }

    function poll() {
      if (!statusUrl) {
        return;
      }

      fetch(statusUrl, {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (payload) {
          if (!payload || payload.ok !== true) {
            return;
          }

          applyRuntimeState(payload);
          const nextStatus = payload.runtime && payload.runtime.status ? payload.runtime.status : "idle";
          if (previousStatus === "running" && nextStatus !== "running") {
            window.location.reload();
            return;
          }
          previousStatus = nextStatus;
          if (nextStatus !== "running") {
            stop();
          }
        })
        .catch(function () {
          return;
        });
    }

    function start() {
      if (timerId) {
        return;
      }
      poll();
      timerId = window.setInterval(poll, Math.max(2, pollSeconds) * 1000);
    }

    if (panel.getAttribute("data-stablecoin-running") === "true") {
      start();
    }

    window.addEventListener("pageshow", function () {
      poll();
    });

    return { start: start };
  }

  function setupRefresh(poller) {
    const form = document.querySelector("[data-stablecoin-refresh-form]");
    const button = document.querySelector("[data-stablecoin-refresh-button]");
    if (!(form instanceof HTMLFormElement) || !(button instanceof HTMLButtonElement)) {
      return;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (button.disabled) {
        return;
      }

      button.disabled = true;
      button.textContent = "更新中";

      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              throw new Error("页面没有收到可识别的稳定币刷新结果。");
            })
            .then(function (payload) {
              if (!response.ok || !payload || payload.ok !== true) {
                throw new Error((payload && payload.message) || "稳定币刷新启动失败，请稍后再试。");
              }
              return payload;
            });
        })
        .then(function (payload) {
          applyRuntimeState(payload);
          showFlash("success", payload.message || "稳定币刷新已启动。");
          if (poller && typeof poller.start === "function") {
            poller.start();
          }
        })
        .catch(function (error) {
          button.disabled = false;
          button.textContent = "立即更新";
          showFlash("error", error instanceof Error ? error.message : "稳定币刷新启动失败，请稍后再试。");
        });
    });
  }

  function applyCdnRuntimeState(payload) {
    if (!payload || !payload.runtime) {
      return;
    }

    const runtime = payload.runtime;
    const panel = document.querySelector("[data-cdn-status-panel]");
    const refreshButton = document.querySelector("[data-cdn-refresh-button]");

    updateNodes("[data-cdn-status-label]", runtime.status_label || "待刷新");
    updateNodes("[data-cdn-started-at]", runtime.started_at_label || "尚未刷新");
    updateNodes("[data-cdn-finished-at]", runtime.finished_at_label || "尚未刷新");
    updateNodes("[data-cdn-last-updated], [data-cdn-last-updated-side]", payload.updated_at_label || "尚未抓取");

    const messageNode = document.querySelector("[data-cdn-message]");
    if (messageNode instanceof HTMLElement) {
      const message = runtime.message || "";
      messageNode.textContent = message;
      messageNode.hidden = !message;
    }

    const errorNode = document.querySelector("[data-cdn-error]");
    if (errorNode instanceof HTMLElement) {
      const error = runtime.error || "";
      errorNode.textContent = error;
      errorNode.hidden = !error;
    }

    if (panel instanceof HTMLElement) {
      panel.setAttribute("data-cdn-running", runtime.is_running ? "true" : "false");
      panel.setAttribute("data-cdn-status", runtime.status || "idle");
    }

    if (refreshButton instanceof HTMLButtonElement) {
      refreshButton.disabled = runtime.is_running;
      refreshButton.textContent = runtime.is_running ? "更新中" : "立即更新";
    }
  }

  function setupCdnStatusPolling() {
    const panel = document.querySelector("[data-cdn-status-panel]");
    if (!(panel instanceof HTMLElement)) {
      return {
        start: function () {},
      };
    }

    const statusUrl = panel.getAttribute("data-status-url") || "";
    const pollSeconds = Number.parseInt(panel.getAttribute("data-cdn-poll-seconds") || "5", 10);
    let previousStatus = panel.getAttribute("data-cdn-status") || "idle";
    let timerId = 0;

    function stop() {
      if (!timerId) {
        return;
      }
      window.clearInterval(timerId);
      timerId = 0;
    }

    function poll() {
      if (!statusUrl) {
        return;
      }

      fetch(statusUrl, {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (payload) {
          if (!payload || payload.ok !== true) {
            return;
          }

          applyCdnRuntimeState(payload);
          const nextStatus = payload.runtime && payload.runtime.status ? payload.runtime.status : "idle";
          if (previousStatus === "running" && nextStatus !== "running") {
            window.location.reload();
            return;
          }
          previousStatus = nextStatus;
          if (nextStatus !== "running") {
            stop();
          }
        })
        .catch(function () {
          return;
        });
    }

    function start() {
      if (timerId) {
        return;
      }
      poll();
      timerId = window.setInterval(poll, Math.max(2, pollSeconds) * 1000);
    }

    if (panel.getAttribute("data-cdn-running") === "true") {
      start();
    }

    window.addEventListener("pageshow", function () {
      poll();
    });

    return { start: start };
  }

  function setupCdnRefresh(poller) {
    const form = document.querySelector("[data-cdn-refresh-form]");
    const button = document.querySelector("[data-cdn-refresh-button]");
    if (!(form instanceof HTMLFormElement) || !(button instanceof HTMLButtonElement)) {
      return;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (button.disabled) {
        return;
      }

      button.disabled = true;
      button.textContent = "更新中";

      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              throw new Error("页面没有收到可识别的 CDN 刷新结果。");
            })
            .then(function (payload) {
              if (!response.ok || !payload || payload.ok !== true) {
                throw new Error((payload && payload.message) || "CDN 刷新启动失败，请稍后再试。");
              }
              return payload;
            });
        })
        .then(function (payload) {
          applyCdnRuntimeState(payload);
          showFlash("success", payload.message || "CDN 刷新已启动。");
          if (poller && typeof poller.start === "function") {
            poller.start();
          }
        })
        .catch(function (error) {
          button.disabled = false;
          button.textContent = "立即更新";
          showFlash("error", error instanceof Error ? error.message : "CDN 刷新启动失败，请稍后再试。");
        });
    });
  }

  function applyApplovinRuntimeState(payload) {
    if (!payload || !payload.runtime) {
      return;
    }

    const runtime = payload.runtime;
    const panel = document.querySelector("[data-applovin-status-panel]");
    const refreshButton = document.querySelector("[data-applovin-refresh-button]");

    updateNodes("[data-applovin-status-label]", runtime.status_label || "待刷新");
    updateNodes("[data-applovin-started-at]", runtime.started_at_label || "尚未刷新");
    updateNodes("[data-applovin-finished-at]", runtime.finished_at_label || "尚未刷新");
    updateNodes("[data-applovin-last-updated], [data-applovin-last-updated-side]", payload.updated_at_label || "尚未抓取");

    const messageNode = document.querySelector("[data-applovin-message]");
    if (messageNode instanceof HTMLElement) {
      const message = runtime.message || "";
      messageNode.textContent = message;
      messageNode.hidden = !message;
    }

    const errorNode = document.querySelector("[data-applovin-error]");
    if (errorNode instanceof HTMLElement) {
      const error = runtime.error || "";
      errorNode.textContent = error;
      errorNode.hidden = !error;
    }

    if (panel instanceof HTMLElement) {
      panel.setAttribute("data-applovin-running", runtime.is_running ? "true" : "false");
      panel.setAttribute("data-applovin-status", runtime.status || "idle");
    }

    if (refreshButton instanceof HTMLButtonElement) {
      refreshButton.disabled = runtime.is_running;
      refreshButton.textContent = runtime.is_running ? "刷新中" : "立即刷新";
    }
  }

  function setupApplovinStatusPolling() {
    const panel = document.querySelector("[data-applovin-status-panel]");
    if (!(panel instanceof HTMLElement)) {
      return {
        start: function () {},
        stop: function () {},
        poll: function () {},
      };
    }

    const statusUrl = panel.getAttribute("data-status-url") || "";
    const pollSeconds = Number.parseInt(panel.getAttribute("data-applovin-poll-seconds") || "5", 10);
    let previousStatus = panel.getAttribute("data-applovin-status") || "idle";
    let timerId = 0;

    function stop() {
      if (!timerId) {
        return;
      }
      window.clearInterval(timerId);
      timerId = 0;
    }

    function poll() {
      if (!statusUrl) {
        return;
      }

      fetch(statusUrl, {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (payload) {
          if (!payload || payload.ok !== true) {
            return;
          }

          applyApplovinRuntimeState(payload);
          const nextStatus = payload.runtime && payload.runtime.status ? payload.runtime.status : "idle";
          if (previousStatus === "running" && nextStatus !== "running") {
            stop();
            reloadCurrentApplovinSelection({
              historyMode: "replace",
              force: true,
            });
            return;
          }
          previousStatus = nextStatus;
          if (nextStatus !== "running") {
            stop();
          }
        })
        .catch(function () {
          return;
        });
    }

    function start() {
      if (timerId) {
        return;
      }
      poll();
      timerId = window.setInterval(poll, Math.max(2, pollSeconds) * 1000);
    }

    if (panel.getAttribute("data-applovin-running") === "true") {
      start();
    }

    if (!applovinPageshowBound) {
      window.addEventListener("pageshow", function () {
        if (activeApplovinPoller && typeof activeApplovinPoller.poll === "function") {
          activeApplovinPoller.poll();
        }
      });
      applovinPageshowBound = true;
    }

    return { start: start, stop: stop, poll: poll };
  }

  function setupApplovinRefresh(poller) {
    const form = document.querySelector("[data-applovin-refresh-form]");
    const button = document.querySelector("[data-applovin-refresh-button]");
    if (!(form instanceof HTMLFormElement) || !(button instanceof HTMLButtonElement)) {
      return;
    }
    if (form.getAttribute("data-applovin-refresh-bound") === "true") {
      return;
    }
    form.setAttribute("data-applovin-refresh-bound", "true");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (button.disabled) {
        return;
      }

      button.disabled = true;
      button.textContent = "刷新中";

      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              throw new Error("页面没有收到可识别的 AppLovin 刷新结果。");
            })
            .then(function (payload) {
              if (!response.ok || !payload || payload.ok !== true) {
                throw new Error((payload && payload.message) || "AppLovin 刷新启动失败，请稍后再试。");
              }
              return payload;
            });
        })
        .then(function (payload) {
          applyApplovinRuntimeState(payload);
          showFlash("success", payload.message || "AppLovin 刷新已启动。");
          if (poller && typeof poller.start === "function") {
            poller.start();
          }
        })
        .catch(function (error) {
          button.disabled = false;
          button.textContent = "立即刷新";
          showFlash("error", error instanceof Error ? error.message : "AppLovin 刷新启动失败，请稍后再试。");
        });
    });
  }

  function setupApplovinFilters() {
    const form = document.querySelector("[data-applovin-filter-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (form.getAttribute("data-applovin-filter-bound") === "true") {
      bindApplovinNavLinks();
      return;
    }
    form.setAttribute("data-applovin-filter-bound", "true");

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const targetUrl = buildApplovinUrlFromForm(form);
      if (!targetUrl) {
        return;
      }
      loadApplovinSelection(targetUrl, {
        historyMode: "push",
      });
    });

    const platformSelect = form.querySelector("[data-applovin-platform-select]");
    const categorySelect = form.querySelector("[data-applovin-category-select]");
    [platformSelect, categorySelect].forEach(function (node) {
      if (!(node instanceof HTMLSelectElement)) {
        return;
      }
      node.addEventListener("change", function () {
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
          return;
        }
        form.submit();
      });
    });

    bindApplovinNavLinks();
  }

  function buildApplovinUrlFromForm(form) {
    if (!(form instanceof HTMLFormElement)) {
      return "";
    }

    const targetUrl = new URL(form.action || window.location.href, window.location.href);
    const formData = new FormData(form);
    formData.forEach(function (value, key) {
      if (typeof value !== "string") {
        return;
      }
      targetUrl.searchParams.set(key, value);
    });
    return targetUrl.toString();
  }

  function getApplovinCurrentUrl() {
    const shell = document.querySelector("[data-applovin-panel-shell]");
    if (shell instanceof HTMLElement) {
      const currentUrl = shell.getAttribute("data-applovin-current-url") || "";
      if (currentUrl) {
        return new URL(currentUrl, window.location.href).toString();
      }
    }
    return new URL(window.location.href).toString();
  }

  function setApplovinLoadingState(isLoading) {
    ["[data-applovin-hero-shell]", "[data-applovin-subnav-shell]", "[data-applovin-panel-shell]"].forEach(function (selector) {
      const node = document.querySelector(selector);
      if (node instanceof HTMLElement) {
        node.classList.toggle("is-loading", Boolean(isLoading));
      }
    });

    document
      .querySelectorAll("[data-applovin-platform-select], [data-applovin-category-select], [data-applovin-refresh-button]")
      .forEach(function (node) {
        if ("disabled" in node) {
          node.disabled = Boolean(isLoading);
        }
      });
  }

  function replaceApplovinShell(selector, incomingDocument) {
    const currentNode = document.querySelector(selector);
    const nextNode = incomingDocument.querySelector(selector);
    if (!(currentNode instanceof HTMLElement) || !(nextNode instanceof HTMLElement)) {
      return false;
    }
    currentNode.replaceWith(nextNode);
    return true;
  }

  function resetCdnTrendEntries() {
    hideActiveCdnTrendTooltip();
    cdnTrendEntries.length = 0;
    activeCdnTrendProvider = "";
  }

  function resetGpuPriceChartEntries() {
    hideActiveGpuPriceTooltip();
    gpuPriceChartEntries.length = 0;
    activeGpuPriceFamily = "";
  }

  function getApplovinPlatformBadgeMarkup(platformId) {
    const normalized = String(platformId || "").trim().toLowerCase();
    if (normalized === "ios" || normalized === "appstore" || normalized === "app-store") {
      return (
        '<svg class="applovin-platform-badge-icon applovin-platform-badge-icon-store" viewBox="0 0 64 64" aria-hidden="true">' +
        '<rect x="5" y="5" width="54" height="54" rx="14" fill="#1f92f4"></rect>' +
        '<path d="M5 19 C5 11.2 11.2 5 19 5 H45 C52.8 5 59 11.2 59 19 V28 H5 Z" fill="#2dc8ff"></path>' +
        '<g fill="none" stroke="#ffffff" stroke-linecap="round" stroke-linejoin="round" stroke-width="5.2">' +
        '<path d="M24 43 L39.5 16"></path>' +
        '<path d="M29 16 L42.5 40"></path>' +
        '<path d="M18.5 34 H45.5"></path>' +
        '</g>' +
        "</svg>"
      );
    }

    return (
      '<svg class="applovin-platform-badge-icon applovin-platform-badge-icon-play" viewBox="0 0 64 64" aria-hidden="true">' +
      '<polygon points="11,8 33.5,30 24.5,38.5 11,52.5" fill="#34a853"></polygon>' +
      '<polygon points="11,8 42.5,26.5 33.5,30 24.5,21.5" fill="#4285f4"></polygon>' +
      '<polygon points="33.5,30 42.5,26.5 52.5,32 38.5,36.5" fill="#ea4335"></polygon>' +
      '<polygon points="24.5,38.5 33.5,30 38.5,36.5 11,52.5" fill="#fbbc04"></polygon>' +
      "</svg>"
    );
  }

  function renderApplovinDonutShell(shell) {
    if (!(shell instanceof HTMLElement)) {
      return;
    }

    const seed = parseJsonNode(shell.querySelector("[data-applovin-donut-seed]"));
    if (!seed) {
      return;
    }

    const segments = Array.isArray(seed.segments)
      ? seed.segments.filter(function (item) {
          return item && Number(item.value || 0) > 0;
        })
      : [];

    if (!segments.length) {
      shell.innerHTML = '<div class="empty-card"><p>Current selection does not expose a readable AppLovin breakdown yet.</p></div>';
      return;
    }

    const chartKey = String(seed.chart_key || "");
    const isShareGauge = chartKey === "app-share-split" || chartKey === "download-share-split";
    const platformBadge = getApplovinPlatformBadgeMarkup(shell.getAttribute("data-applovin-platform") || "");
    shell.setAttribute("data-applovin-chart-kind", isShareGauge ? "share" : "split");

    if (isShareGauge) {
      const primary = segments[0];
      const radius = 52;
      const circumference = 2 * Math.PI * radius;
      const visibleArc = circumference * 0.78;
      const gaugeValue = Math.max(0, Math.min(100, Number(primary.share_pct || primary.value || 0)));
      const activeArc = Math.max(0, Number(((visibleArc * gaugeValue) / 100).toFixed(2)));
      const hiddenArc = Math.max(0, Number((circumference - visibleArc).toFixed(2)));
      const gaugeColor = escapeHtml(String(primary.color || "#4f8df7"));
      const supportLabel = chartKey === "app-share-split" ? "Category coverage" : "Download coverage";

      shell.innerHTML =
        '<div class="applovin-share-card">' +
        '<div class="applovin-share-gauge-shell">' +
        '<svg class="applovin-share-gauge-svg" viewBox="0 0 160 160" role="img"></svg>' +
        `<div class="applovin-share-badge">${platformBadge}</div>` +
        "</div>" +
        '<div class="applovin-share-copy">' +
        `<span class="applovin-share-kicker">${escapeHtml(supportLabel)}</span>` +
        `<strong class="applovin-share-value" style="--applovin-share-color:${gaugeColor}">${escapeHtml(
          String(primary.value_label || primary.share_label || "")
        )}</strong>` +
        `<span class="applovin-share-total">${escapeHtml(String(seed.total_label || "n/a"))} total</span>` +
        "</div>" +
        "</div>";

      const svg = shell.querySelector("svg");
      if (!(svg instanceof SVGSVGElement)) {
        return;
      }

      svg.setAttribute("aria-label", String(seed.title || "AppLovin share chart"));
      svg.innerHTML =
        `<g transform="rotate(138 80 80)">` +
        `<circle class="applovin-share-gauge-track" cx="80" cy="80" r="${radius}" stroke-dasharray="${visibleArc.toFixed(
          2
        )} ${hiddenArc.toFixed(2)}"></circle>` +
        `<circle class="applovin-share-gauge-value" cx="80" cy="80" r="${radius}" stroke="${gaugeColor}" stroke-dasharray="${activeArc.toFixed(
          2
        )} ${(circumference - activeArc).toFixed(2)}"></circle>` +
        `</g>`;
      return;
    }

    const radius = 54;
    const circumference = 2 * Math.PI * radius;
    const totalValue = segments.reduce(function (sum, item) {
      return sum + Math.max(0, Number(item.value || 0));
    }, 0);
    let consumedRatio = 0;
    const ringsMarkup = segments
      .map(function (item) {
        const ratio = totalValue > 0 ? Math.max(0, Number(item.value || 0)) / totalValue : 0;
        const dash = Math.max(0, Number((circumference * ratio).toFixed(2)));
        const gap = Math.max(0, Number((circumference - dash).toFixed(2)));
        const segment = `<circle class="applovin-split-ring-segment" cx="90" cy="90" r="${radius}" fill="none" stroke="${escapeHtml(
          String(item.color || "#4f8df7")
        )}" stroke-dasharray="${dash} ${gap}" stroke-dashoffset="${Number((-consumedRatio * circumference).toFixed(2))}"></circle>`;
        consumedRatio += ratio;
        return segment;
      })
      .join("");

    const statsMarkup = segments
      .map(function (item) {
        return (
          '<article class="applovin-split-stat">' +
          `<span>${escapeHtml(String(item.label || ""))}</span>` +
          `<strong style="--applovin-stat-color:${escapeHtml(String(item.color || "#4f8df7"))}">${escapeHtml(
            String(item.value_label || "")
          )}</strong>` +
          `<small>${escapeHtml(String(item.share_label || ""))}</small>` +
          "</article>"
        );
      })
      .join("");

    shell.innerHTML =
      '<div class="applovin-split-card">' +
      '<div class="applovin-split-visual">' +
      '<svg class="applovin-split-svg" viewBox="0 0 180 180" role="img"></svg>' +
      `<div class="applovin-split-badge">${platformBadge}</div>` +
      "</div>" +
      `<div class="applovin-split-stats">${statsMarkup}</div>` +
      "</div>" +
      `<div class="applovin-split-total">${escapeHtml(String(seed.total_label || "n/a"))} total</div>`;

    const svg = shell.querySelector("svg");
    if (!(svg instanceof SVGSVGElement)) {
      return;
    }

    svg.setAttribute("aria-label", String(seed.title || "AppLovin mix chart"));
    svg.innerHTML =
      `<circle class="applovin-split-ring-track" cx="90" cy="90" r="${radius}"></circle>` +
      `<g transform="rotate(-90 90 90)">${ringsMarkup}</g>`;
  }

  function renderApplovinDonuts() {
    document.querySelectorAll("[data-applovin-donut]").forEach(function (shell) {
      renderApplovinDonutShell(shell);
    });
    applovinDonutsInitialized = true;
  }

  function buildVisualSignature(nodes) {
    return nodes
      .map(function (node, index) {
        if (!(node instanceof HTMLElement)) {
          return `node-${index}`;
        }
        return [
          node.getAttribute("data-chart-key") || "",
          node.getAttribute("data-chart-title") || "",
          node.getAttribute("data-trend-namespace") || "",
          node.getAttribute("data-applovin-platform") || "",
          index,
        ].join(":");
      })
      .join("|");
  }

  function updateTrendControlButtons(namespace) {
    const resolvedNamespace = String(namespace || "cdn").trim() || "cdn";
    const state = ensureTrendControlState(resolvedNamespace);
    document.querySelectorAll(`[data-trend-controls][data-trend-namespace="${resolvedNamespace}"]`).forEach(function (group) {
      if (!(group instanceof HTMLElement)) {
        return;
      }

      group.querySelectorAll("[data-trend-window]").forEach(function (button) {
        if (!(button instanceof HTMLButtonElement)) {
          return;
        }
        const isActive = String(button.getAttribute("data-trend-window") || "").trim().toLowerCase() === state.window;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });

      group.querySelectorAll("[data-trend-view]").forEach(function (button) {
        if (!(button instanceof HTMLButtonElement)) {
          return;
        }
        const isActive = String(button.getAttribute("data-trend-view") || "").trim().toLowerCase() === state.view;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
    });
  }

  function setupTrendControls() {
    document.querySelectorAll("[data-trend-controls]").forEach(function (group) {
      if (!(group instanceof HTMLElement)) {
        return;
      }

      const namespace = getTrendControlNamespace(group);
      updateTrendControlButtons(namespace);

      if (group.getAttribute("data-trend-controls-bound") === "true") {
        return;
      }
      group.setAttribute("data-trend-controls-bound", "true");

      group.addEventListener("click", function (event) {
        const target = event.target instanceof Element ? event.target.closest("[data-trend-window], [data-trend-view]") : null;
        if (!(target instanceof HTMLButtonElement)) {
          return;
        }

        event.preventDefault();
        const state = ensureTrendControlState(namespace);
        let changed = false;

        if (target.hasAttribute("data-trend-window")) {
          const nextWindow = String(target.getAttribute("data-trend-window") || TREND_WINDOW_DEFAULT).trim().toLowerCase();
          const resolvedWindow = Object.prototype.hasOwnProperty.call(TREND_WINDOW_DAY_MAP, nextWindow)
            ? nextWindow
            : TREND_WINDOW_DEFAULT;
          if (resolvedWindow !== state.window) {
            state.window = resolvedWindow;
            changed = true;
          }
        }

        if (target.hasAttribute("data-trend-view")) {
          const nextView = String(target.getAttribute("data-trend-view") || TREND_VIEW_DEFAULT).trim().toLowerCase();
          const resolvedView = ["raw", "smooth", "indexed"].indexOf(nextView) >= 0 ? nextView : TREND_VIEW_DEFAULT;
          if (resolvedView !== state.view) {
            state.view = resolvedView;
            changed = true;
          }
        }

        if (!changed) {
          return;
        }

        updateTrendControlButtons(namespace);
        if (cdnTrendEntries.length) {
          renderAllCdnTrendCharts();
        } else if (document.querySelector("[data-cdn-trend-chart]")) {
          initializeCdnTrendCharts();
        }
      });
    });
  }

  function initializeStablecoinVisuals() {
    if (stablecoinVisualsInitialized) {
      return;
    }
    getChartEntries();
    setupChartScrollbars();
    renderAllCharts();
    setupLegendFilter();
    setupChartHover();
    stablecoinVisualsInitialized = true;
  }

  function scheduleStablecoinVisualInitialization(force) {
    const shells = Array.from(document.querySelectorAll("[data-stablecoin-chart]")).filter(function (node) {
      return node instanceof HTMLElement;
    });
    if (!shells.length) {
      return;
    }
    if (force) {
      stablecoinVisualsInitialized = false;
    }
    if (stablecoinVisualsInitialized) {
      return;
    }
    queueWhenNearViewport(shells, function () {
      initializeStablecoinVisuals();
    });
  }

  function scheduleCdnTrendVisualInitialization(force) {
    const shells = Array.from(document.querySelectorAll("[data-cdn-trend-chart]")).filter(function (node) {
      return node instanceof HTMLElement;
    });
    if (!shells.length) {
      resetCdnTrendEntries();
      cdnTrendVisualsInitialized = false;
      cdnTrendVisualSignature = "";
      return;
    }
    const nextSignature = buildVisualSignature(shells);
    if (force || nextSignature !== cdnTrendVisualSignature) {
      resetCdnTrendEntries();
      cdnTrendVisualSignature = nextSignature;
      cdnTrendVisualsInitialized = false;
    }
    if (cdnTrendVisualsInitialized) {
      return;
    }
    queueWhenNearViewport(shells, function () {
      initializeCdnTrendCharts();
    });
  }

  function scheduleApplovinDonutInitialization(force) {
    const shells = Array.from(document.querySelectorAll("[data-applovin-donut]")).filter(function (node) {
      return node instanceof HTMLElement;
    });
    if (!shells.length) {
      return;
    }
    const nextSignature = buildVisualSignature(shells);
    if (force || nextSignature !== applovinDonutSignature) {
      applovinDonutSignature = nextSignature;
      applovinDonutsInitialized = false;
    }
    if (applovinDonutsInitialized) {
      return;
    }
    queueWhenNearViewport(shells, function () {
      renderApplovinDonuts();
    });
  }

  function initializeCdnTrendCharts() {
    resetCdnTrendEntries();
    getCdnTrendEntries();
    setupCdnTrendScrollbars();
    renderAllCdnTrendCharts();
    setupCdnTrendLegendFilter();
    setupCdnTrendHover();
    setupTrendControls();
    updateTrendControlButtons("cdn");
    updateTrendControlButtons("applovin");
    cdnTrendVisualsInitialized = true;
  }

  function initializeApplovinInteractiveState() {
    if (!(document.querySelector("[data-applovin-panel-shell]") instanceof HTMLElement)) {
      return;
    }

    if (activeApplovinPoller && typeof activeApplovinPoller.stop === "function") {
      activeApplovinPoller.stop();
    }

    activeApplovinPoller = setupApplovinStatusPolling();
    setupApplovinRefresh(activeApplovinPoller);
    setupApplovinFilters();
    setupTrendControls();
    scheduleCdnTrendVisualInitialization(true);
    scheduleApplovinDonutInitialization(true);
    setupApplovinHistoryNavigation();
  }

  function loadApplovinSelection(targetUrl, options) {
    const settings = options || {};
    const nextUrl = new URL(targetUrl || window.location.href, window.location.href);
    const targetTab = nextUrl.searchParams.get("tab") || "stablecoins";
    if (targetTab !== "applovin") {
      window.location.assign(nextUrl.toString());
      return Promise.resolve(false);
    }

    const currentUrl = getApplovinCurrentUrl();
    if (!settings.force && nextUrl.toString() === currentUrl) {
      return Promise.resolve(true);
    }

    if (applovinRequestController) {
      applovinRequestController.abort();
    }

    const controller = new AbortController();
    applovinRequestController = controller;
    setApplovinLoadingState(true);

    return fetch(nextUrl.toString(), {
      headers: {
        Accept: "text/html",
        "X-Requested-With": "XMLHttpRequest",
      },
      signal: controller.signal,
    })
      .then(function (response) {
        return response.text().then(function (html) {
          if (!response.ok) {
            throw new Error("AppLovin monitor view could not be loaded.");
          }
          return html;
        });
      })
      .then(function (html) {
        const parser = new DOMParser();
        const incomingDocument = parser.parseFromString(html, "text/html");
        const hasHero = replaceApplovinShell("[data-applovin-hero-shell]", incomingDocument);
        const hasSubnav = replaceApplovinShell("[data-applovin-subnav-shell]", incomingDocument);
        const hasPanel = replaceApplovinShell("[data-applovin-panel-shell]", incomingDocument);

        if (!hasHero || !hasSubnav || !hasPanel) {
          window.location.assign(nextUrl.toString());
          return false;
        }

        if (incomingDocument.title) {
          document.title = incomingDocument.title;
        }

        if (settings.historyMode === "replace") {
          window.history.replaceState({ tab: "applovin" }, "", nextUrl.toString());
        } else if (settings.historyMode !== "silent" && nextUrl.toString() !== window.location.href) {
          window.history.pushState({ tab: "applovin" }, "", nextUrl.toString());
        }

        initializeApplovinInteractiveState();
        return true;
      })
      .catch(function (error) {
        if (error && error.name === "AbortError") {
          return false;
        }
        showFlash("error", error instanceof Error ? error.message : "AppLovin monitor view could not be updated.");
        return false;
      })
      .finally(function () {
        if (applovinRequestController === controller) {
          applovinRequestController = null;
        }
        setApplovinLoadingState(false);
      });
  }

  function reloadCurrentApplovinSelection(options) {
    return loadApplovinSelection(getApplovinCurrentUrl(), {
      historyMode: "replace",
      force: true,
      ...(options || {}),
    });
  }

  function bindApplovinNavLinks() {
    document.querySelectorAll("[data-applovin-nav-link]").forEach(function (link) {
      if (!(link instanceof HTMLAnchorElement) || link.getAttribute("data-applovin-nav-bound") === "true") {
        return;
      }

      link.setAttribute("data-applovin-nav-bound", "true");
      link.addEventListener("click", function (event) {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
          return;
        }
        event.preventDefault();
        loadApplovinSelection(link.href, {
          historyMode: "push",
        });
      });
    });
  }

  function setupApplovinHistoryNavigation() {
    if (applovinHistoryBound) {
      return;
    }
    applovinHistoryBound = true;

    window.addEventListener("popstate", function () {
      if (!(document.querySelector("[data-applovin-panel-shell]") instanceof HTMLElement)) {
        return;
      }

      const targetUrl = new URL(window.location.href);
      const targetTab = targetUrl.searchParams.get("tab") || "stablecoins";
      if (targetTab !== "applovin") {
        window.location.assign(targetUrl.toString());
        return;
      }

      loadApplovinSelection(targetUrl.toString(), {
        historyMode: "replace",
        force: true,
      });
    });
  }

  function renderCdnMetaChips(items) {
    if (!Array.isArray(items) || !items.length) {
      return "";
    }

    return (
      '<div class="cdn-chip-row">' +
      items
        .map(function (item) {
          return `<span class="meta-chip">${escapeHtml(item)}</span>`;
        })
        .join("") +
      "</div>"
    );
  }

  function renderCdnProviderBadge(provider, color, secondaryLabel) {
    const secondary = String(secondaryLabel || "").trim();
    return (
      '<span class="detail-chip cdn-provider-badge">' +
      `<span class="stablecoin-inline-swatch" style="--stablecoin-color: ${escapeHtml(color || "#94a3b8")}"></span>` +
      `<strong>${escapeHtml(provider || "Unknown")}</strong>` +
      (secondary ? `<span>${escapeHtml(secondary)}</span>` : "") +
      "</span>"
    );
  }

  function renderCdnSiteRow(site) {
    const rankLabel = String(site.rank_label || "").trim() || "-";
    const siteLabel = String(site.label || "").trim() || "Unknown";
    const siteHref = String(site.final_url || site.url || "").trim();
    const siteTitleMarkup = siteHref
      ? `<a class="text-link" href="${escapeHtml(siteHref)}" target="_blank" rel="noreferrer">${escapeHtml(siteLabel)}</a>`
      : `<span>${escapeHtml(siteLabel)}</span>`;
    const rowMetaBadges = Array.isArray(site.row_meta_badges) ? site.row_meta_badges : [];
    const observedBadges = Array.isArray(site.observed_provider_badges_compact) ? site.observed_provider_badges_compact : [];
    const observedExtraCount = Math.max(0, Number(site.observed_provider_extra_count || 0));
    const providerEvidence = Array.isArray(site.provider_evidence) ? site.provider_evidence : [];
    const providerEvidenceTitle = providerEvidence.length
      ? providerEvidence.map(function (item) { return String(item || ""); }).join(" · ")
      : String(site.provider_evidence_preview || "");
    const providerEvidencePreview = String(site.provider_evidence_preview || "").trim();
    const assetHostCountLabel = String(site.asset_host_count_label || "").trim();
    const assetHostNames = Array.isArray(site.asset_host_names_compact) ? site.asset_host_names_compact : [];
    const assetHostTitle = assetHostNames.length ? assetHostNames.join(" · ") : assetHostCountLabel;
    const assetHostPreview = assetHostCountLabel
      ? (
          assetHostCountLabel +
          (assetHostNames.length ? ` · ${assetHostNames.join(" · ")}` : "")
        )
      : "";
    const entryHostLabel = String(site.entry_host_label || site.url || "").trim();
    const compactSummary = String(site.compact_summary || "").trim();
    const summaryTitle = String(site.error_label || compactSummary || "").trim();

    return (
      "<tr>" +
      `<td class="cdn-site-cell-rank">${escapeHtml(rankLabel)}</td>` +
      '<td class="cdn-site-cell-site">' +
      `<div class="cdn-site-title">${siteTitleMarkup}</div>` +
      renderCdnMetaChips(rowMetaBadges) +
      "</td>" +
      '<td class="cdn-site-cell-primary">' +
      renderCdnProviderBadge(site.provider, site.provider_color, site.provider_confidence) +
      (providerEvidencePreview
        ? `<p class="field-help cdn-site-inline-copy" title="${escapeHtml(providerEvidenceTitle)}">${escapeHtml(providerEvidencePreview)}</p>`
        : "") +
      "</td>" +
      '<td class="cdn-site-cell-observed">' +
      '<div class="cdn-chip-row">' +
      observedBadges
        .map(function (badge) {
          return renderCdnProviderBadge(badge.label, badge.color, "");
        })
        .join("") +
      (observedExtraCount ? `<span class="meta-chip">+${escapeHtml(observedExtraCount)}</span>` : "") +
      "</div>" +
      (assetHostPreview
        ? `<p class="field-help cdn-site-inline-copy" title="${escapeHtml(assetHostTitle || assetHostPreview)}">${escapeHtml(assetHostPreview)}</p>`
        : "") +
      "</td>" +
      '<td class="cdn-site-cell-summary">' +
      `<p class="section-caption cdn-site-inline-copy" title="${escapeHtml(entryHostLabel)}">${escapeHtml(entryHostLabel)}</p>` +
      (compactSummary
        ? `<p class="field-help cdn-site-inline-copy" title="${escapeHtml(summaryTitle || compactSummary)}">${escapeHtml(compactSummary)}</p>`
        : "") +
      "</td>" +
      "</tr>"
    );
  }

  function setupCdnSiteDetails() {
    const details = document.querySelector("[data-cdn-sites-details]");
    if (!(details instanceof HTMLDetailsElement)) {
      return;
    }

    const url = String(details.getAttribute("data-cdn-sites-url") || "").trim();
    const shell = details.querySelector("[data-cdn-sites-shell]");
    const body = details.querySelector("[data-cdn-sites-body]");
    const loading = details.querySelector("[data-cdn-sites-loading]");
    const error = details.querySelector("[data-cdn-sites-error]");
    const errorCopy = details.querySelector("[data-cdn-sites-error-copy]");
    const empty = details.querySelector("[data-cdn-sites-empty]");

    if (!(shell instanceof HTMLElement) || !(body instanceof HTMLElement)) {
      return;
    }

    function applyState(nextState, message) {
      details.setAttribute("data-cdn-sites-state", nextState);
      if (loading instanceof HTMLElement) {
        loading.hidden = nextState !== "loading";
      }
      if (error instanceof HTMLElement) {
        error.hidden = nextState !== "error";
      }
      if (empty instanceof HTMLElement) {
        empty.hidden = nextState !== "empty";
      }
      shell.hidden = nextState !== "loaded";
      if (errorCopy instanceof HTMLElement && typeof message === "string" && message) {
        errorCopy.textContent = message;
      }
    }

    function loadSites() {
      if (!url) {
        applyState("error", "逐站点结果接口缺失，暂时无法读取明细。");
        return;
      }

      const currentState = details.getAttribute("data-cdn-sites-state") || "idle";
      if (currentState === "loading" || currentState === "loaded") {
        return;
      }

      applyState("loading");

      fetch(url, {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              throw new Error("站点明细接口没有返回可识别的 JSON。");
            })
            .then(function (payload) {
              if (!response.ok || !payload || payload.ok !== true) {
                throw new Error((payload && payload.message) || "逐站点结果加载失败，请稍后重试。");
              }
              return payload;
            });
        })
        .then(function (payload) {
          const sites = Array.isArray(payload.sites) ? payload.sites : [];
          body.innerHTML = "";

          if (!sites.length) {
            applyState("empty");
            return;
          }

          body.innerHTML = sites.map(renderCdnSiteRow).join("");
          applyState("loaded");
        })
        .catch(function (loadError) {
          body.innerHTML = "";
          applyState(
            "error",
            loadError instanceof Error ? loadError.message : "逐站点结果加载失败，请稍后重试。"
          );
        });
    }

    details.addEventListener("toggle", function () {
      if (!details.open) {
        return;
      }
      loadSites();
    });

    if (details.open) {
      loadSites();
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatCompactCurrency(value) {
    const amount = Number(value || 0);
    const absolute = Math.abs(amount);
    if (absolute >= 1000000000000) {
      return `$${(amount / 1000000000000).toFixed(absolute >= 100000000000000 ? 0 : 1)}T`;
    }
    if (absolute >= 1000000000) {
      return `$${(amount / 1000000000).toFixed(absolute >= 100000000000 ? 0 : 1)}B`;
    }
    if (absolute >= 1000000) {
      return `$${(amount / 1000000).toFixed(absolute >= 100000000 ? 0 : 1)}M`;
    }
    if (absolute >= 1000) {
      return `$${(amount / 1000).toFixed(absolute >= 100000 ? 0 : 1)}K`;
    }
    return `$${amount.toFixed(amount >= 100 ? 0 : 1)}`.replace(".0", "");
  }

  function parseJsonNode(node) {
    if (!(node instanceof HTMLScriptElement)) {
      return null;
    }

    try {
      return JSON.parse(node.textContent || "null");
    } catch (error) {
      return null;
    }
  }

  function ensureTrendControlState(namespace) {
    const resolvedNamespace = String(namespace || "cdn").trim() || "cdn";
    if (!trendControlState[resolvedNamespace]) {
      trendControlState[resolvedNamespace] = {
        window: TREND_WINDOW_DEFAULT,
        view: TREND_VIEW_DEFAULT,
      };
    }
    return trendControlState[resolvedNamespace];
  }

  function getTrendControlNamespace(node) {
    if (!(node instanceof HTMLElement)) {
      return "cdn";
    }
    return String(node.getAttribute("data-trend-namespace") || "cdn").trim() || "cdn";
  }

  function parseTrendPointTime(value) {
    const text = String(value || "").trim();
    if (!text) {
      return Number.NaN;
    }
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : Number.NaN;
  }

  function queueWhenNearViewport(targets, callback) {
    const nodes = (Array.isArray(targets) ? targets : []).filter(function (item) {
      return item instanceof HTMLElement;
    });
    if (typeof callback !== "function") {
      return;
    }
    if (!nodes.length) {
      callback();
      return;
    }
    if (typeof IntersectionObserver !== "function") {
      callback();
      return;
    }

    let triggered = false;
    const observer = new IntersectionObserver(
      function (entries) {
        if (
          triggered ||
          !entries.some(function (entry) {
            return entry.isIntersecting || entry.intersectionRatio > 0;
          })
        ) {
          return;
        }
        triggered = true;
        observer.disconnect();
        callback();
      },
      {
        rootMargin: "240px 0px",
      }
    );

    nodes.forEach(function (node) {
      observer.observe(node);
    });
  }

  function getChartEntries() {
    if (chartEntries.length) {
      return chartEntries;
    }

    document.querySelectorAll("[data-stablecoin-chart]").forEach(function (shell) {
      if (!(shell instanceof HTMLElement)) {
        return;
      }

      const viewport = shell.querySelector("[data-chart-viewport]");
      const svg = shell.querySelector("svg");
      const scrollbar = shell.querySelector("[data-chart-scrollbar]");
      const scrollbarInner = shell.querySelector("[data-chart-scrollbar-inner]");
      const note = shell.querySelector("[data-chart-filter-note]");
      const seedNode = shell.querySelector("[data-stablecoin-chart-seed]");
      const seed = parseJsonNode(seedNode);
      if (!(viewport instanceof HTMLElement) || !(svg instanceof SVGSVGElement) || !seed) {
        return;
      }

      chartEntries.push({
        shell: shell,
        viewport: viewport,
        svg: svg,
        scrollbar: scrollbar instanceof HTMLElement ? scrollbar : null,
        scrollbarInner: scrollbarInner instanceof HTMLElement ? scrollbarInner : null,
        note: note instanceof HTMLElement ? note : null,
        seed: seed,
        visibleBarLimit: Math.max(
          1,
          Number.parseInt(shell.getAttribute("data-chart-visible-limit") || String(CHART_DEFAULT_VISIBLE_BARS), 10) ||
            CHART_DEFAULT_VISIBLE_BARS
        ),
      });
    });

    return chartEntries;
  }

  function buildFilteredBar(sourceBar, symbol) {
    const series = Array.isArray(sourceBar.series) ? sourceBar.series : [];
    const filteredSeries = symbol
      ? series.filter(function (item) {
          return String(item.symbol || "").toUpperCase() === symbol;
        })
      : series.slice();

    const totalValue = symbol
      ? filteredSeries.reduce(function (sum, item) {
          return sum + Number(item.value || 0);
        }, 0)
      : Number(sourceBar.total_value || 0);

    const totalLabel = symbol
      ? filteredSeries.length
        ? String(filteredSeries[0].value_label || formatCompactCurrency(totalValue))
        : formatCompactCurrency(totalValue)
      : String(sourceBar.total_label || formatCompactCurrency(totalValue));

    return {
      label: String(sourceBar.label || ""),
      month: String(sourceBar.month || ""),
      totalValue: totalValue,
      totalLabel: totalLabel,
      series: filteredSeries.map(function (item) {
        return {
          symbol: String(item.symbol || ""),
          label: String(item.label || ""),
          color: String(item.color || "var(--stablecoin-series-1)"),
          value: Number(item.value || 0),
          valueLabel: String(item.value_label || formatCompactCurrency(item.value || 0)),
        };
      }),
    };
  }

  function buildChartState(seed, symbol) {
    const sourceBars = Array.isArray(seed.bars) ? seed.bars : [];
    const bars = sourceBars.map(function (bar) {
      return buildFilteredBar(bar, symbol);
    });

    const margin = {
      top: 56,
      right: 28,
      bottom: 88,
      left: 92,
    };
    const visibleBarLimit = Math.max(
      1,
      Number.parseInt(seed.visible_bar_limit || seed.visibleBarLimit || CHART_DEFAULT_VISIBLE_BARS, 10) ||
        CHART_DEFAULT_VISIBLE_BARS
    );
    const visibleBarCount = Math.max(1, Math.min(bars.length || 1, visibleBarLimit));
    const width = Math.max(
      CHART_MIN_WIDTH,
      margin.left + margin.right + bars.length * CHART_BAR_WIDTH + Math.max(0, bars.length - 1) * CHART_BAR_GAP
    );
    const viewportWidth = Math.max(
      CHART_MIN_WIDTH,
      margin.left +
        margin.right +
        visibleBarCount * CHART_BAR_WIDTH +
        Math.max(0, visibleBarCount - 1) * CHART_BAR_GAP
    );
    const height = CHART_HEIGHT;
    const plotHeight = height - margin.top - margin.bottom;
    const baselineY = height - margin.bottom;
    const maxTotal = Math.max(
      1,
      bars.reduce(function (largest, bar) {
        return Math.max(largest, bar.totalValue);
      }, 0)
    );

    const ticks = [0, 0.25, 0.5, 0.75, 1].map(function (ratio) {
      const y = baselineY - plotHeight * ratio;
      return {
        y: Number(y.toFixed(2)),
        label: formatCompactCurrency(maxTotal * ratio),
      };
    });

    const plottedBars = bars.map(function (bar, index) {
      const x = margin.left + index * (CHART_BAR_WIDTH + CHART_BAR_GAP);
      let currentY = baselineY;
      const segments = bar.series.map(function (segment) {
        const rawHeight = maxTotal > 0 ? (segment.value / maxTotal) * plotHeight : 0;
        const heightValue = Number(rawHeight.toFixed(2));
        const y = Number((currentY - heightValue).toFixed(2));
        currentY = y;
        return {
          x: x,
          y: y,
          width: CHART_BAR_WIDTH,
          height: heightValue,
          fill: segment.color,
          symbol: segment.symbol,
          value: segment.value,
          valueLabel: segment.valueLabel,
        };
      });

      const totalHeight = Number((baselineY - currentY).toFixed(2));
      const topY = Number((baselineY - totalHeight).toFixed(2));

      return {
        label: bar.label,
        month: bar.month,
        x: x,
        width: CHART_BAR_WIDTH,
        totalHeight: totalHeight,
        topY: topY,
        labelY: baselineY + 34,
        totalY: Math.max(30, topY - 12),
        hoverLeft: x - 12,
        hoverTop: margin.top - 14,
        hoverWidth: CHART_BAR_WIDTH + 24,
        hoverHeight: plotHeight + 30,
        totalLabel: bar.totalLabel,
        series: bar.series,
        segments: segments,
      };
    });

    return {
      width: width,
      viewportWidth: viewportWidth,
      height: height,
      margin: margin,
      baselineY: baselineY,
      plotHeight: plotHeight,
      ticks: ticks,
      bars: plottedBars,
      symbol: symbol,
      isScrollable: bars.length > visibleBarLimit,
      visibleBarLimit: visibleBarLimit,
    };
  }

  function buildGradientMarkup(seed, bars) {
    const seen = new Set();
    const gradients = [];

    bars.forEach(function (bar) {
      bar.series.forEach(function (series) {
        const symbol = String(series.symbol || "").toUpperCase();
        if (!symbol || seen.has(symbol)) {
          return;
        }
        seen.add(symbol);
        gradients.push(
          `<linearGradient id="${escapeHtml(seed.chart_key)}-gradient-${escapeHtml(symbol.toLowerCase())}" x1="0" y1="0" x2="0" y2="1">` +
            `<stop offset="0%" style="stop-color:${escapeHtml(series.color)};stop-opacity:0.78"></stop>` +
            `<stop offset="100%" style="stop-color:${escapeHtml(series.color)};stop-opacity:1"></stop>` +
          "</linearGradient>"
        );
      });
    });

    return gradients.join("");
  }

  function buildChartMarkup(seed, state) {
    const chartKey = String(seed.chart_key || "stablecoin");
    const defs = buildGradientMarkup(seed, state.bars);
    const axisLeft = state.margin.left - 12;
    const axisRight = state.width - state.margin.right + 6;
    const baselineMarkup =
      `<line class="stablecoin-chart-baseline" x1="${state.margin.left - 6}" y1="${state.baselineY}" x2="${state.width - state.margin.right + 6}" y2="${state.baselineY}"></line>`;

    const ticksMarkup = state.ticks
      .map(function (tick) {
        return (
          `<g class="stablecoin-chart-tick">` +
            `<line class="stablecoin-chart-grid" x1="${state.margin.left - 6}" y1="${tick.y}" x2="${axisRight}" y2="${tick.y}"></line>` +
            `<text class="stablecoin-chart-axis" x="${axisLeft}" y="${tick.y + 4}">${escapeHtml(tick.label)}</text>` +
          `</g>`
        );
      })
      .join("");

    const barsMarkup = state.bars
      .map(function (bar, index) {
        const barTitle = escapeHtml(String(seed.title || ""));
        const barSeriesJson = escapeHtml(JSON.stringify(bar.series));
        const segmentsMarkup = bar.segments
          .map(function (segment) {
            if (segment.height <= 0) {
              return "";
            }
            return (
              `<rect class="stablecoin-chart-segment" x="${segment.x}" y="${segment.y}" width="${segment.width}" height="${segment.height}" fill="url(#${escapeHtml(chartKey)}-gradient-${escapeHtml(String(segment.symbol || "").toLowerCase())})" data-series-symbol="${escapeHtml(segment.symbol)}"></rect>`
            );
          })
          .join("");

        const outlineMarkup =
          bar.totalHeight > 0
            ? `<rect class="stablecoin-chart-outline" x="${bar.x}" y="${bar.topY}" width="${bar.width}" height="${bar.totalHeight}" rx="8" ry="8"></rect>`
            : "";

        return (
          `<g class="stablecoin-chart-bar" data-chart-bar data-bar-title="${barTitle}" data-bar-month="${escapeHtml(bar.month)}" data-bar-total-label="${escapeHtml(bar.totalLabel)}" data-bar-series="${barSeriesJson}" tabindex="0">` +
            `<rect class="stablecoin-chart-hover-band" x="${bar.hoverLeft}" y="${bar.hoverTop}" width="${bar.hoverWidth}" height="${bar.hoverHeight}" rx="16" ry="16"></rect>` +
            `${segmentsMarkup}` +
            `${outlineMarkup}` +
            `<text class="stablecoin-chart-total" x="${bar.x + (bar.width / 2)}" y="${bar.totalY}">${escapeHtml(bar.totalLabel)}</text>` +
            `<text class="stablecoin-chart-month" x="${bar.x + (bar.width / 2)}" y="${bar.labelY}">${escapeHtml(bar.label)}</text>` +
            `<rect class="stablecoin-chart-hitbox" x="${bar.hoverLeft}" y="${bar.hoverTop}" width="${bar.hoverWidth}" height="${bar.hoverHeight}" rx="16" ry="16"></rect>` +
          `</g>`
        );
      })
      .join("");

    return `<defs>${defs}</defs>${ticksMarkup}${baselineMarkup}${barsMarkup}`;
  }

  function renderChart(entry, symbol) {
    entry.seed.visible_bar_limit = entry.visibleBarLimit;
    const state = buildChartState(entry.seed, symbol);
    entry.svg.setAttribute("viewBox", `0 0 ${state.width} ${state.height}`);
    entry.svg.setAttribute("aria-label", symbol ? `${entry.seed.title} - ${symbol}` : String(entry.seed.title || ""));
    entry.svg.innerHTML = buildChartMarkup(entry.seed, state);
    entry.svg.style.width = state.isScrollable ? `${state.width}px` : "100%";
    entry.svg.style.minWidth = `${state.isScrollable ? state.width : Math.min(state.width, state.viewportWidth)}px`;
    if (entry.viewport instanceof HTMLElement) {
      entry.viewport.style.maxWidth = state.isScrollable ? `${state.viewportWidth}px` : "100%";
      entry.viewport.scrollLeft = 0;
    }
    entry.shell.classList.toggle("is-scrollable-x", state.isScrollable);
    entry.shell.setAttribute("data-active-symbol", symbol || "");
    entry.shell.setAttribute("data-chart-scrollable", state.isScrollable ? "true" : "false");

    if (entry.scrollbar instanceof HTMLElement && entry.scrollbarInner instanceof HTMLElement) {
      entry.scrollbar.hidden = !state.isScrollable;
      entry.scrollbarInner.style.width = `${state.width}px`;
      entry.scrollbar.scrollLeft = 0;
    }

    if (entry.note instanceof HTMLElement) {
      const baseNote = symbol
        ? `Focused on ${symbol}. Click the same legend chip again to restore all stablecoins.`
        : "Click a stablecoin legend item above to isolate its monthly trend.";
      entry.note.textContent = state.isScrollable
        ? `${baseNote} Older months can be reviewed with the horizontal scrollbar below.`
        : baseNote;
    }

    if (false && entry.note instanceof HTMLElement) {
      const baseNote = symbol
        ? `当前聚焦 ${symbol}，再次点击图例可恢复全部稳定币。`
        : "点击上方币种，单独查看它的月度趋势。";
      entry.note.textContent = state.isScrollable
        ? `${baseNote} 图表超过 ${state.visibleBarLimit} 根柱子后，可在下方拖动横向滑动条查看更早月份。`
        : baseNote;
    }

    if (state.isScrollable && entry.viewport instanceof HTMLElement) {
      window.requestAnimationFrame(function () {
        const targetScrollLeft = Math.max(0, state.width - entry.viewport.clientWidth);
        entry.viewport.scrollLeft = targetScrollLeft;
        if (entry.scrollbar instanceof HTMLElement) {
          entry.scrollbar.scrollLeft = targetScrollLeft;
        }
      });
    } else if (entry.viewport instanceof HTMLElement) {
      entry.viewport.scrollLeft = 0;
      if (entry.scrollbar instanceof HTMLElement) {
        entry.scrollbar.scrollLeft = 0;
      }
    }
  }

  function setupChartScrollbars() {
    getChartEntries().forEach(function (entry) {
      if (!(entry.viewport instanceof HTMLElement) || !(entry.scrollbar instanceof HTMLElement)) {
        return;
      }

      let isSyncing = false;
      const syncScroll = function (source, target) {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        target.scrollLeft = source.scrollLeft;
        window.requestAnimationFrame(function () {
          isSyncing = false;
        });
      };

      entry.viewport.addEventListener("scroll", function () {
        syncScroll(entry.viewport, entry.scrollbar);
      });

      entry.scrollbar.addEventListener("scroll", function () {
        syncScroll(entry.scrollbar, entry.viewport);
      });
    });
  }

  function updateLegendState() {
    document.querySelectorAll("[data-stablecoin-legend]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      const symbol = String(button.getAttribute("data-stablecoin-legend") || "").toUpperCase();
      const isActive = Boolean(activeLegendSymbol) && symbol === activeLegendSymbol;
      const isDimmed = Boolean(activeLegendSymbol) && symbol !== activeLegendSymbol;

      button.classList.toggle("is-active", isActive);
      button.classList.toggle("is-dimmed", isDimmed);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function renderAllCharts() {
    hideActiveChartTooltip();
    getChartEntries().forEach(function (entry) {
      renderChart(entry, activeLegendSymbol);
    });
    updateLegendState();
  }

  function setupLegendFilter() {
    const buttons = Array.from(document.querySelectorAll("[data-stablecoin-legend]"));
    if (!buttons.length) {
      return;
    }

    buttons.forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      button.addEventListener("click", function (event) {
        event.preventDefault();
        const symbol = String(button.getAttribute("data-stablecoin-legend") || "").toUpperCase();
        activeLegendSymbol = activeLegendSymbol === symbol ? "" : symbol;
        renderAllCharts();
      });
    });

    updateLegendState();
  }

  function ensureChartTooltip() {
    let tooltip = document.querySelector("[data-stablecoin-chart-tooltip]");
    if (tooltip instanceof HTMLElement) {
      return tooltip;
    }

    tooltip = document.createElement("div");
    tooltip.className = "stablecoin-chart-tooltip";
    tooltip.setAttribute("data-stablecoin-chart-tooltip", "");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function formatSeriesRows(series) {
    return series
      .filter(function (item) {
        return item && Number(item.value || 0) >= 0;
      })
      .sort(function (left, right) {
        return Number(right.value || 0) - Number(left.value || 0);
      })
      .map(function (item) {
        const symbol = escapeHtml(String(item.symbol || ""));
        const color = escapeHtml(String(item.color || "var(--stablecoin-series-1)"));
        const valueLabel = escapeHtml(String(item.valueLabel || item.value_label || formatCompactCurrency(item.value || 0)));
        return (
          '<li class="stablecoin-chart-tooltip-row">' +
          `<span class="stablecoin-chart-tooltip-key"><span class="stablecoin-chart-tooltip-swatch" style="--stablecoin-color:${color}"></span>${symbol}</span>` +
          `<strong>${valueLabel}</strong>` +
          "</li>"
        );
      })
      .join("");
  }

  function positionTooltip(tooltip, x, y) {
    if (!(tooltip instanceof HTMLElement)) {
      return;
    }

    const offset = 18;
    const tooltipRect = tooltip.getBoundingClientRect();
    let left = x + offset;
    let top = y - 18;

    if (left + tooltipRect.width > window.innerWidth - 18) {
      left = x - tooltipRect.width - offset;
    }
    if (left < 12) {
      left = 12;
    }
    if (top + tooltipRect.height > window.innerHeight - 12) {
      top = window.innerHeight - tooltipRect.height - 12;
    }
    if (top < 12) {
      top = 12;
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function findBarNode(target) {
    if (!(target instanceof Element)) {
      return null;
    }
    return target.closest("[data-chart-bar]");
  }

  function setupChartHover() {
    const entries = getChartEntries();
    if (!entries.length) {
      return;
    }

    const tooltip = ensureChartTooltip();
    let activeBar = null;

    function hideTooltip() {
      if (tooltip instanceof HTMLElement) {
        tooltip.hidden = true;
        tooltip.classList.remove("is-visible");
      }
      if (activeBar instanceof SVGGElement) {
        activeBar.classList.remove("is-active");
      }
      activeBar = null;
    }

    function showTooltip(bar, x, y) {
      if (!(bar instanceof SVGGElement) || !(tooltip instanceof HTMLElement)) {
        return;
      }

      const month = String(bar.getAttribute("data-bar-month") || "");
      const title = String(bar.getAttribute("data-bar-title") || "");
      const total = String(bar.getAttribute("data-bar-total-label") || "");
      let series = [];
      try {
        series = JSON.parse(bar.getAttribute("data-bar-series") || "[]");
      } catch (error) {
        series = [];
      }

      if (activeBar instanceof SVGGElement && activeBar !== bar) {
        activeBar.classList.remove("is-active");
      }
      activeBar = bar;
      activeBar.classList.add("is-active");

      tooltip.innerHTML =
        `<div class="stablecoin-chart-tooltip-head"><span>${escapeHtml(month)}</span><strong>${escapeHtml(title)}</strong></div>` +
        `<div class="stablecoin-chart-tooltip-total"><span>总量</span><strong>${escapeHtml(total)}</strong></div>` +
        `<ul class="stablecoin-chart-tooltip-list">${formatSeriesRows(series)}</ul>`;
      tooltip.hidden = false;
      tooltip.classList.add("is-visible");

      if (typeof x === "number" && typeof y === "number") {
        positionTooltip(tooltip, x, y);
        return;
      }

      const rect = bar.getBoundingClientRect();
      positionTooltip(tooltip, rect.left + rect.width / 2, rect.top + rect.height / 2);
    }

    entries.forEach(function (entry) {
      entry.shell.addEventListener("pointermove", function (event) {
        const bar = findBarNode(event.target);
        if (!(bar instanceof SVGGElement)) {
          hideTooltip();
          return;
        }
        showTooltip(bar, event.clientX, event.clientY);
      });

      entry.shell.addEventListener("pointerleave", function () {
        hideTooltip();
      });

      entry.shell.addEventListener("focusin", function (event) {
        const bar = findBarNode(event.target);
        if (!(bar instanceof SVGGElement)) {
          return;
        }
        showTooltip(bar);
      });

      entry.shell.addEventListener("focusout", function (event) {
        if (!(event.currentTarget instanceof HTMLElement)) {
          hideTooltip();
          return;
        }

        const nextTarget = event.relatedTarget;
        if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
          return;
        }
        hideTooltip();
      });
    });

    window.addEventListener("scroll", hideTooltip, true);
    window.addEventListener("resize", hideTooltip);
    hideActiveChartTooltip = hideTooltip;
  }

  function getCdnTrendEntries() {
    if (cdnTrendEntries.length) {
      return cdnTrendEntries;
    }

    document.querySelectorAll("[data-cdn-trend-chart]").forEach(function (shell) {
      if (!(shell instanceof HTMLElement)) {
        return;
      }

      const viewport = shell.querySelector("[data-cdn-chart-viewport]");
      const svg = shell.querySelector("svg");
      const scrollbar = shell.querySelector("[data-cdn-chart-scrollbar]");
      const scrollbarInner = shell.querySelector("[data-cdn-chart-scrollbar-inner]");
      const note = shell.querySelector("[data-cdn-chart-filter-note]");
      const seedNode = shell.querySelector("[data-cdn-trend-chart-seed]");
      const seed = parseJsonNode(seedNode);
      if (!(viewport instanceof HTMLElement) || !(svg instanceof SVGSVGElement) || !seed) {
        return;
      }

      cdnTrendEntries.push({
        shell: shell,
        viewport: viewport,
        svg: svg,
        scrollbar: scrollbar instanceof HTMLElement ? scrollbar : null,
        scrollbarInner: scrollbarInner instanceof HTMLElement ? scrollbarInner : null,
        note: note instanceof HTMLElement ? note : null,
        seed: seed,
        namespace: getTrendControlNamespace(shell),
        filterable: shell.getAttribute("data-chart-filterable") !== "false",
        title: shell.getAttribute("data-chart-title") || String(seed.title || ""),
        visiblePointLimit: Math.max(
          1,
          Number.parseInt(shell.getAttribute("data-chart-visible-limit") || String(CDN_TREND_DEFAULT_VISIBLE_POINTS), 10) ||
            CDN_TREND_DEFAULT_VISIBLE_POINTS
        ),
      });
    });

    return cdnTrendEntries;
  }

  function formatCompactCount(value) {
    const amount = Number(value || 0);
    const absolute = Math.abs(amount);
    if (absolute >= 1000000000000) {
      return `${(amount / 1000000000000).toFixed(absolute >= 100000000000000 ? 0 : 1)}T`.replace(".0T", "T");
    }
    if (absolute >= 1000000000) {
      return `${(amount / 1000000000).toFixed(absolute >= 100000000000 ? 0 : 1)}B`.replace(".0B", "B");
    }
    if (absolute >= 1000000) {
      return `${(amount / 1000000).toFixed(absolute >= 100000000 ? 0 : 1)}M`.replace(".0M", "M");
    }
    if (absolute >= 1000) {
      return `${(amount / 1000).toFixed(absolute >= 100000 ? 0 : 1)}K`.replace(".0K", "K");
    }
    return `${Math.round(amount)}`;
  }

  function formatCdnTrendValue(value, metricKind, axisMode) {
    const amount = Number(value || 0);
    if (metricKind === "index") {
      const precision = axisMode ? (Math.abs(amount) >= 10 ? 0 : 1) : 1;
      return amount.toFixed(precision).replace(".0", "");
    }
    if (metricKind === "share_pct") {
      const precision = axisMode ? (amount >= 10 ? 0 : 1) : 1;
      return `${amount.toFixed(precision).replace(".0", "")}%`;
    }
    return formatCompactCount(amount);
  }

  function buildFilteredCdnTrendPoint(sourcePoint, providerName) {
    const series = Array.isArray(sourcePoint.series) ? sourcePoint.series : [];
    const filteredSeries = providerName
      ? series.filter(function (item) {
          return String(item.symbol || "") === providerName;
        })
      : series.slice();

    return {
      label: String(sourcePoint.label || ""),
      pointLabel: String(sourcePoint.point_label || sourcePoint.pointLabel || ""),
      pointAt: String(sourcePoint.point_at || sourcePoint.pointAt || ""),
      trackedCount: Number(sourcePoint.tracked_count || sourcePoint.trackedCount || 0),
      reachableCount: Number(sourcePoint.reachable_count || sourcePoint.reachableCount || 0),
      multiProviderCount: Number(sourcePoint.multi_provider_count || sourcePoint.multiProviderCount || 0),
      series: filteredSeries.map(function (item) {
        return {
          symbol: String(item.symbol || ""),
          label: String(item.label || item.symbol || ""),
          color: String(item.color || "#4f8df7"),
          value: Number(item.value || 0),
          valueLabel: String(item.value_label || item.valueLabel || formatCdnTrendValue(item.value || 0, "count", false)),
          secondaryLabel: String(item.secondary_label || item.secondaryLabel || ""),
        };
      }),
    };
  }

  function buildSmoothCdnTrendPath(points) {
    if (!Array.isArray(points) || !points.length) {
      return "";
    }
    if (points.length === 1) {
      return `M ${points[0].x} ${points[0].y}`;
    }
    if (points.length === 2) {
      return points
        .map(function (point, index) {
          return `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`;
        })
        .join(" ");
    }

    let path = `M ${points[0].x} ${points[0].y}`;
    for (let index = 0; index < points.length - 1; index += 1) {
      const previous = points[Math.max(0, index - 1)];
      const current = points[index];
      const next = points[index + 1];
      const nextNext = points[Math.min(points.length - 1, index + 2)];
      const control1X = current.x + (next.x - previous.x) / 6;
      const control1Y = current.y + (next.y - previous.y) / 6;
      const control2X = next.x - (nextNext.x - current.x) / 6;
      const control2Y = next.y - (nextNext.y - current.y) / 6;
      path +=
        ` C ${control1X.toFixed(2)} ${control1Y.toFixed(2)}` +
        `, ${control2X.toFixed(2)} ${control2Y.toFixed(2)}` +
        `, ${next.x} ${next.y}`;
    }
    return path;
  }

  function resolveCdnTrendPointGap(pointCount) {
    const total = Math.max(0, Number(pointCount || 0));
    if (total >= 45) {
      return 28;
    }
    if (total >= 30) {
      return 34;
    }
    if (total >= 18) {
      return 42;
    }
    return CDN_TREND_POINT_GAP;
  }

  function filterTrendPointsByWindow(points, windowKey) {
    const normalizedWindow = String(windowKey || TREND_WINDOW_DEFAULT).trim().toLowerCase();
    const limitDays = TREND_WINDOW_DAY_MAP[normalizedWindow];
    if (!limitDays) {
      return points.slice();
    }

    const latestTimestamp = points.reduce(function (largest, point) {
      const parsed = parseTrendPointTime(point.pointAt);
      return Number.isFinite(parsed) ? Math.max(largest, parsed) : largest;
    }, 0);

    if (latestTimestamp > 0) {
      const cutoff = latestTimestamp - (limitDays - 1) * 24 * 60 * 60 * 1000;
      const filtered = points.filter(function (point) {
        const parsed = parseTrendPointTime(point.pointAt);
        return !Number.isFinite(parsed) || parsed >= cutoff;
      });
      if (filtered.length) {
        return filtered;
      }
    }

    return points.slice(-Math.min(points.length, limitDays));
  }

  function applyTrendViewMode(points, viewMode, metricKind) {
    const normalizedView = String(viewMode || TREND_VIEW_DEFAULT).trim().toLowerCase();
    const clonedPoints = points.map(function (point) {
      return {
        ...point,
        series: point.series.map(function (item) {
          return {
            ...item,
          };
        }),
      };
    });

    if (normalizedView === "raw") {
      return {
        points: clonedPoints,
        metricKind: metricKind,
      };
    }

    const symbols = [];
    clonedPoints.forEach(function (point) {
      point.series.forEach(function (item) {
        const symbol = String(item.symbol || "");
        if (symbol && symbols.indexOf(symbol) < 0) {
          symbols.push(symbol);
        }
      });
    });

    if (normalizedView === "smooth") {
      symbols.forEach(function (symbol) {
        const values = clonedPoints.map(function (point) {
          const seriesItem = point.series.find(function (item) {
            return String(item.symbol || "") === symbol;
          });
          return Number(seriesItem && seriesItem.value ? seriesItem.value : 0);
        });
        clonedPoints.forEach(function (point, index) {
          const seriesItem = point.series.find(function (item) {
            return String(item.symbol || "") === symbol;
          });
          if (!seriesItem) {
            return;
          }
          const neighbors = [values[index - 1], values[index], values[index + 1]].filter(function (item) {
            return Number.isFinite(item);
          });
          const smoothedValue = neighbors.length
            ? neighbors.reduce(function (sum, item) {
                return sum + Number(item || 0);
              }, 0) / neighbors.length
            : Number(seriesItem.value || 0);
          seriesItem.value = Number(smoothedValue.toFixed(metricKind === "share_pct" ? 2 : 1));
          seriesItem.valueLabel = formatCdnTrendValue(seriesItem.value, metricKind, false);
          if (seriesItem.secondaryLabel) {
            seriesItem.secondaryLabel = `${seriesItem.secondaryLabel} · 3pt avg`;
          }
        });
      });
      return {
        points: clonedPoints,
        metricKind: metricKind,
      };
    }

    if (normalizedView === "indexed") {
      symbols.forEach(function (symbol) {
        let baseValue = Number.NaN;
        clonedPoints.forEach(function (point) {
          const seriesItem = point.series.find(function (item) {
            return String(item.symbol || "") === symbol;
          });
          if (!seriesItem || Number.isFinite(baseValue)) {
            return;
          }
          const candidate = Number(seriesItem.value || 0);
          if (Number.isFinite(candidate) && candidate > 0) {
            baseValue = candidate;
          }
        });
        clonedPoints.forEach(function (point) {
          const seriesItem = point.series.find(function (item) {
            return String(item.symbol || "") === symbol;
          });
          if (!seriesItem) {
            return;
          }
          const nextValue =
            Number.isFinite(baseValue) && baseValue > 0
              ? (Number(seriesItem.value || 0) / baseValue) * 100
              : 0;
          seriesItem.value = Number(nextValue.toFixed(1));
          seriesItem.valueLabel = formatCdnTrendValue(seriesItem.value, "index", false);
          seriesItem.secondaryLabel = "100 = first visible point";
        });
      });
      return {
        points: clonedPoints,
        metricKind: "index",
      };
    }

    return {
      points: clonedPoints,
      metricKind: metricKind,
    };
  }

  function buildCdnTrendState(seed, providerName) {
    const sourcePoints = Array.isArray(seed.points) ? seed.points : [];
    const namespace = String(seed.namespace || "cdn").trim() || "cdn";
    const controlState = ensureTrendControlState(namespace);
    const basePoints = sourcePoints.map(function (point) {
      return buildFilteredCdnTrendPoint(point, providerName);
    });
    const windowedPoints = filterTrendPointsByWindow(basePoints, controlState.window);
    const transformed = applyTrendViewMode(windowedPoints, controlState.view, String(seed.metric_kind || "count"));
    const points = transformed.points;
    const displayMetricKind = transformed.metricKind;
    const margin = {
      top: 24,
      right: 18,
      bottom: 84,
      left: 60,
    };
    const visiblePointLimit = Math.max(
      1,
      Number.parseInt(seed.visible_point_limit || seed.visiblePointLimit || CDN_TREND_DEFAULT_VISIBLE_POINTS, 10) ||
        CDN_TREND_DEFAULT_VISIBLE_POINTS
    );
    const visiblePointCount = Math.max(1, Math.min(points.length || 1, visiblePointLimit));
    const pointGap = resolveCdnTrendPointGap(points.length);
    const width = Math.max(
      CDN_TREND_MIN_WIDTH,
      margin.left + margin.right + Math.max(0, points.length - 1) * pointGap + 36
    );
    const viewportWidth = Math.max(
      CDN_TREND_MIN_WIDTH,
      margin.left + margin.right + Math.max(0, visiblePointCount - 1) * pointGap + 36
    );
    const height = CDN_TREND_HEIGHT;
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const baselineY = height - margin.bottom;
    const step = points.length > 1 ? plotWidth / (points.length - 1) : 0;
    const values = points.reduce(function (result, point) {
      point.series.forEach(function (item) {
        result.push(Number(item.value || 0));
      });
      return result;
    }, []);
    const rawMaxValue = Math.max(1, ...values);
    const rawMinValue = values.length ? Math.min(...values) : 0;
    let minValue = 0;
    let maxValue = rawMaxValue <= 1 ? 1 : rawMaxValue * 1.08;
    if (displayMetricKind === "index") {
      minValue = rawMinValue > 0 ? rawMinValue * 0.96 : 0;
      maxValue = rawMaxValue > 0 ? rawMaxValue * 1.04 : 120;
      if (maxValue - minValue < 8) {
        maxValue = minValue + 8;
      }
    }
    const valueRange = Math.max(1, maxValue - minValue);
    const tickRatios = [0, 0.25, 0.5, 0.75, 1];
    const ticks = tickRatios.map(function (ratio) {
      const value = minValue + valueRange * ratio;
      const y = baselineY - plotHeight * ratio;
      return {
        y: Number(y.toFixed(2)),
        label: formatCdnTrendValue(value, displayMetricKind, true),
      };
    });

    const plottedPoints = points.map(function (point, index) {
      const x = points.length === 1 ? margin.left + plotWidth / 2 : margin.left + index * step;
      const bandWidth = points.length > 1 ? Math.min(68, Math.max(54, step * 0.74)) : 72;
      const series = point.series.map(function (item) {
        const y = baselineY - (((Number(item.value || 0) - minValue) / valueRange) * plotHeight);
        return {
          symbol: item.symbol,
          label: item.label,
          color: item.color,
          value: item.value,
          valueLabel: item.valueLabel,
          secondaryLabel: item.secondaryLabel,
          x: Number(x.toFixed(2)),
          y: Number(y.toFixed(2)),
        };
      });
      return {
        label: point.label,
        pointLabel: point.pointLabel,
        pointAt: point.pointAt,
        trackedCount: point.trackedCount,
        reachableCount: point.reachableCount,
        multiProviderCount: point.multiProviderCount,
        x: Number(x.toFixed(2)),
        labelY: baselineY + 42,
        hoverLeft: Number((x - bandWidth / 2).toFixed(2)),
        hoverTop: margin.top - 12,
        hoverWidth: Number(bandWidth.toFixed(2)),
        hoverHeight: plotHeight + 22,
        series: series,
      };
    });

    const lineIndex = new Map();
    plottedPoints.forEach(function (point) {
      point.series.forEach(function (item) {
        const key = String(item.symbol || "");
        if (!lineIndex.has(key)) {
          lineIndex.set(key, {
            symbol: key,
            label: item.label,
            color: item.color,
            points: [],
          });
        }
        lineIndex.get(key).points.push(item);
      });
    });

    const lines = Array.from(lineIndex.values()).map(function (line) {
      return {
        symbol: line.symbol,
        label: line.label,
        color: line.color,
        points: line.points,
        path: buildSmoothCdnTrendPath(line.points),
      };
    });

    return {
      width: width,
      viewportWidth: viewportWidth,
      height: height,
      baselineY: baselineY,
      margin: margin,
      ticks: ticks,
      points: plottedPoints,
      lines: lines,
      namespace: namespace,
      viewMode: controlState.view,
      windowKey: controlState.window,
      displayMetricKind: displayMetricKind,
      maxValue: maxValue,
      minValue: minValue,
      isScrollable: points.length > visiblePointLimit,
      visiblePointLimit: visiblePointLimit,
    };
  }

  function buildCdnTrendChartMarkup(seed, state) {
    const axisLeft = state.margin.left - 12;
    const axisRight = state.width - state.margin.right + 6;
    const ticksMarkup = state.ticks
      .map(function (tick) {
        return (
          `<g class="cdn-trend-tick">` +
          `<line class="cdn-trend-grid-line" x1="${state.margin.left - 6}" y1="${tick.y}" x2="${axisRight}" y2="${tick.y}"></line>` +
          `<text class="cdn-trend-axis" x="${axisLeft}" y="${tick.y + 4}">${escapeHtml(tick.label)}</text>` +
          `</g>`
        );
      })
      .join("");
    const baselineMarkup = `<line class="cdn-trend-baseline" x1="${state.margin.left - 6}" y1="${state.baselineY}" x2="${axisRight}" y2="${state.baselineY}"></line>`;
    const linesMarkup = state.lines
      .map(function (line) {
        const pointsMarkup = line.points
          .map(function (point) {
            return `<circle class="cdn-trend-point-node" cx="${point.x}" cy="${point.y}" r="4" style="--cdn-provider-color:${escapeHtml(line.color)}"></circle>`;
          })
          .join("");
        return (
          `<g class="cdn-trend-line-group" data-provider-symbol="${escapeHtml(line.symbol)}">` +
          `<path class="cdn-trend-line" d="${escapeHtml(line.path)}" style="--cdn-provider-color:${escapeHtml(line.color)}"></path>` +
          pointsMarkup +
          `</g>`
        );
      })
      .join("");
    const columnsMarkup = state.points
      .map(function (point) {
        const pointSeriesJson = escapeHtml(JSON.stringify(point.series));
        return (
          `<g class="cdn-trend-column" data-cdn-trend-point data-point-label="${escapeHtml(point.pointLabel)}" data-point-series="${pointSeriesJson}" tabindex="0">` +
          `<rect class="cdn-trend-hover-band" x="${point.hoverLeft}" y="${point.hoverTop}" width="${point.hoverWidth}" height="${point.hoverHeight}" rx="16" ry="16"></rect>` +
          `<text class="cdn-trend-label" x="${point.x}" y="${point.labelY}" transform="rotate(-18 ${point.x} ${point.labelY})">${escapeHtml(point.label)}</text>` +
          `<rect class="cdn-trend-hitbox" x="${point.hoverLeft}" y="${point.hoverTop}" width="${point.hoverWidth}" height="${point.hoverHeight}" rx="16" ry="16"></rect>` +
          `</g>`
        );
      })
      .join("");

    return `${ticksMarkup}${baselineMarkup}${linesMarkup}${columnsMarkup}`;
  }

  function renderCdnTrendChart(entry, providerName) {
    const activeProvider = entry.filterable ? providerName : "";
    entry.seed.namespace = entry.namespace;
    entry.seed.visible_point_limit = entry.visiblePointLimit;
    const state = buildCdnTrendState(entry.seed, activeProvider);
    entry.svg.setAttribute("viewBox", `0 0 ${state.width} ${state.height}`);
    entry.svg.setAttribute(
      "aria-label",
      activeProvider ? `${entry.seed.title} - ${activeProvider}` : String(entry.seed.title || entry.title || "")
    );
    entry.svg.innerHTML = buildCdnTrendChartMarkup(entry.seed, state);
    entry.svg.style.width = state.isScrollable ? `${state.width}px` : "100%";
    entry.svg.style.minWidth = `${state.isScrollable ? state.width : Math.min(state.width, state.viewportWidth)}px`;

    if (entry.viewport instanceof HTMLElement) {
      entry.viewport.style.maxWidth = state.isScrollable ? `${state.viewportWidth}px` : "100%";
      entry.viewport.scrollLeft = 0;
    }

    if (entry.scrollbar instanceof HTMLElement && entry.scrollbarInner instanceof HTMLElement) {
      entry.scrollbar.hidden = !state.isScrollable;
      entry.scrollbarInner.style.width = `${state.width}px`;
      entry.scrollbar.scrollLeft = 0;
    }

    entry.shell.classList.toggle("is-scrollable-x", state.isScrollable);
    entry.shell.setAttribute("data-active-provider", activeProvider || "");

    if (entry.note instanceof HTMLElement) {
      const trendState = ensureTrendControlState(entry.namespace);
      const windowLabel = String(trendState.window || TREND_WINDOW_DEFAULT).toUpperCase();
      let baseNote = entry.filterable
        ? "Click a legend item above to isolate one series across time."
        : String(entry.seed.subtitle || "Stored daily snapshots will make the trend easier to read over time.");
      if (state.points.length < 2) {
        baseNote = entry.filterable
          ? "Only a few snapshots are stored right now. As more refreshes land, the trend will become clearer."
          : "Only a few snapshots are stored right now. As more daily crawls land, this chart will gain shape.";
      } else if (entry.filterable && activeProvider) {
        baseNote = `Focused on ${activeProvider}. Click the same legend chip again to restore all series.`;
      }
      if (trendState.view === "smooth") {
        baseNote = `${baseNote} Smoothed view uses a three-point rolling average.`;
      } else if (trendState.view === "indexed") {
        baseNote = `${baseNote} Indexed view sets the first visible point to 100.`;
      }
      entry.note.textContent = state.isScrollable
        ? `${baseNote} Window: ${windowLabel}. Older snapshots can be reviewed with the horizontal scrollbar below.`
        : `${baseNote} Window: ${windowLabel}.`;
    }

    if (false && entry.note instanceof HTMLElement) {
      let baseNote = "点击上方 provider，单独查看它在时间序列里的变化。";
      if (state.points.length < 2) {
        baseNote = "目前历史快照还不多，继续刷新后这里会更容易看出趋势。";
      } else if (providerName) {
        baseNote = `当前聚焦 ${providerName}，再次点击图例可恢复全部 provider。`;
      }
      entry.note.textContent = state.isScrollable
        ? `${baseNote} 快照点超过 ${state.visiblePointLimit} 个后，可在下方拖动横向滑动条回看更早记录。`
        : baseNote;
    }

    if (state.isScrollable && entry.viewport instanceof HTMLElement) {
      window.requestAnimationFrame(function () {
        const targetScrollLeft = Math.max(0, state.width - entry.viewport.clientWidth);
        entry.viewport.scrollLeft = targetScrollLeft;
        syncCdnTrendScrollbarFromViewport(entry);
      });
      return;
    }

    window.requestAnimationFrame(function () {
      syncCdnTrendScrollbarFromViewport(entry);
    });
  }

  function syncCdnTrendScrollbarFromViewport(entry) {
    if (
      !(entry.viewport instanceof HTMLElement) ||
      !(entry.scrollbar instanceof HTMLElement) ||
      !(entry.scrollbarInner instanceof HTMLElement)
    ) {
      return;
    }

    const maxScrollLeft = Math.max(0, entry.viewport.scrollWidth - entry.viewport.clientWidth);
    const isActuallyScrollable = maxScrollLeft > 1;
    entry.scrollbar.hidden = !isActuallyScrollable;
    entry.scrollbarInner.style.width = `${entry.viewport.scrollWidth}px`;
    entry.scrollbar.scrollLeft = Math.round(Math.min(maxScrollLeft, entry.viewport.scrollLeft));
    entry.shell.classList.toggle("is-scrollable-x", isActuallyScrollable);
  }

  function setupCdnTrendScrollbars() {
    getCdnTrendEntries().forEach(function (entry) {
      if (
        !(entry.viewport instanceof HTMLElement) ||
        !(entry.scrollbar instanceof HTMLElement) ||
        !(entry.scrollbarInner instanceof HTMLElement)
      ) {
        return;
      }
      if (entry.shell.getAttribute("data-cdn-trend-scroll-bound") === "true") {
        return;
      }
      entry.shell.setAttribute("data-cdn-trend-scroll-bound", "true");

      let isSyncing = false;

      entry.viewport.addEventListener("scroll", function () {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        syncCdnTrendScrollbarFromViewport(entry);
        window.requestAnimationFrame(function () {
          isSyncing = false;
        });
      });

      entry.scrollbar.addEventListener("scroll", function () {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        entry.viewport.scrollLeft = entry.scrollbar.scrollLeft;
        window.requestAnimationFrame(function () {
          isSyncing = false;
        });
      });

      syncCdnTrendScrollbarFromViewport(entry);
    });
  }

  function updateCdnTrendLegendState() {
    document.querySelectorAll("[data-cdn-trend-legend]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      const providerName = String(button.getAttribute("data-cdn-trend-legend") || "");
      const isActive = Boolean(activeCdnTrendProvider) && providerName === activeCdnTrendProvider;
      const isDimmed = Boolean(activeCdnTrendProvider) && providerName !== activeCdnTrendProvider;

      button.classList.toggle("is-active", isActive);
      button.classList.toggle("is-dimmed", isDimmed);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function renderAllCdnTrendCharts() {
    hideActiveCdnTrendTooltip();
    getCdnTrendEntries().forEach(function (entry) {
      renderCdnTrendChart(entry, activeCdnTrendProvider);
    });
    updateCdnTrendLegendState();
  }

  function setupCdnTrendLegendFilter() {
    const buttons = Array.from(document.querySelectorAll("[data-cdn-trend-legend]"));
    if (!buttons.length) {
      return;
    }

    buttons.forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      button.addEventListener("click", function (event) {
        event.preventDefault();
        const providerName = String(button.getAttribute("data-cdn-trend-legend") || "");
        activeCdnTrendProvider = activeCdnTrendProvider === providerName ? "" : providerName;
        renderAllCdnTrendCharts();
      });
    });

    updateCdnTrendLegendState();
  }

  function ensureCdnTrendTooltip() {
    let tooltip = document.querySelector("[data-cdn-trend-tooltip]");
    if (tooltip instanceof HTMLElement) {
      return tooltip;
    }

    tooltip = document.createElement("div");
    tooltip.className = "cdn-trend-tooltip";
    tooltip.setAttribute("data-cdn-trend-tooltip", "");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function formatCdnTrendSeriesRows(series) {
    return series
      .slice()
      .sort(function (left, right) {
        return Number(right.value || 0) - Number(left.value || 0);
      })
      .map(function (item) {
        const color = escapeHtml(String(item.color || "#4f8df7"));
        const label = escapeHtml(String(item.label || item.symbol || ""));
        const valueLabel = escapeHtml(String(item.valueLabel || item.value_label || ""));
        const secondaryLabel = escapeHtml(String(item.secondaryLabel || item.secondary_label || ""));
        const secondaryMarkup = secondaryLabel ? `<span>${secondaryLabel}</span>` : "";
        return (
          '<li class="cdn-trend-tooltip-row">' +
          `<span class="cdn-trend-tooltip-key"><span class="cdn-trend-tooltip-swatch" style="--cdn-provider-color:${color}"></span>${label}</span>` +
          `<strong>${valueLabel}</strong>` +
          secondaryMarkup +
          "</li>"
        );
      })
      .join("");
  }

  function findCdnTrendPointNode(target) {
    if (!(target instanceof Element)) {
      return null;
    }
    return target.closest("[data-cdn-trend-point]");
  }

  function setupCdnTrendHover() {
    const entries = getCdnTrendEntries();
    if (!entries.length) {
      return;
    }

    const tooltip = ensureCdnTrendTooltip();
    let activePoint = null;

    function hideTooltip() {
      if (tooltip instanceof HTMLElement) {
        tooltip.hidden = true;
        tooltip.classList.remove("is-visible");
      }
      if (activePoint instanceof SVGGElement) {
        activePoint.classList.remove("is-active");
      }
      activePoint = null;
    }

    function showTooltip(pointNode, x, y) {
      if (!(pointNode instanceof SVGGElement) || !(tooltip instanceof HTMLElement)) {
        return;
      }

      let series = [];
      try {
        series = JSON.parse(pointNode.getAttribute("data-point-series") || "[]");
      } catch (error) {
        series = [];
      }

      if (activePoint instanceof SVGGElement && activePoint !== pointNode) {
        activePoint.classList.remove("is-active");
      }
      activePoint = pointNode;
      activePoint.classList.add("is-active");

      const chartShell = pointNode.closest("[data-cdn-trend-chart]");
      const chartTitle =
        chartShell instanceof HTMLElement ? String(chartShell.getAttribute("data-chart-title") || "Snapshot") : "Snapshot";
      tooltip.innerHTML =
        `<div class="cdn-trend-tooltip-head"><span>${escapeHtml(String(pointNode.getAttribute("data-point-label") || ""))}</span><strong>${escapeHtml(chartTitle)}</strong></div>` +
        `<ul class="cdn-trend-tooltip-list">${formatCdnTrendSeriesRows(series)}</ul>`;
      tooltip.hidden = false;
      tooltip.classList.add("is-visible");

      if (typeof x === "number" && typeof y === "number") {
        positionTooltip(tooltip, x, y);
        return;
      }

      const rect = pointNode.getBoundingClientRect();
      positionTooltip(tooltip, rect.left + rect.width / 2, rect.top + rect.height / 2);
    }

    entries.forEach(function (entry) {
      if (entry.shell.getAttribute("data-cdn-trend-hover-bound") === "true") {
        return;
      }
      entry.shell.setAttribute("data-cdn-trend-hover-bound", "true");

      entry.shell.addEventListener("pointermove", function (event) {
        const pointNode = findCdnTrendPointNode(event.target);
        if (!(pointNode instanceof SVGGElement)) {
          hideTooltip();
          return;
        }
        showTooltip(pointNode, event.clientX, event.clientY);
      });

      entry.shell.addEventListener("pointerleave", function () {
        hideTooltip();
      });

      entry.shell.addEventListener("focusin", function (event) {
        const pointNode = findCdnTrendPointNode(event.target);
        if (!(pointNode instanceof SVGGElement)) {
          return;
        }
        showTooltip(pointNode);
      });

      entry.shell.addEventListener("focusout", function (event) {
        if (!(event.currentTarget instanceof HTMLElement)) {
          hideTooltip();
          return;
        }

        const nextTarget = event.relatedTarget;
        if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
          return;
        }
        hideTooltip();
      });
    });

    if (!cdnTrendWindowBound) {
      window.addEventListener("scroll", hideTooltip, true);
      window.addEventListener("resize", hideTooltip);
      cdnTrendWindowBound = true;
    }
    hideActiveCdnTrendTooltip = hideTooltip;
  }

  function setupGpuPriceRefreshConfirm() {
    document.querySelectorAll("[data-gpu-price-refresh-form]").forEach(function (form) {
      if (!(form instanceof HTMLFormElement) || form.getAttribute("data-gpu-refresh-bound") === "true") {
        return;
      }
      form.setAttribute("data-gpu-refresh-bound", "true");
      form.addEventListener("submit", function (event) {
        const hasFreshToday = form.getAttribute("data-has-fresh-today") === "true";
        const message =
          form.getAttribute("data-confirm-message") ||
          "GPU price index already has today's result. Refresh anyway and keep only the newest daily result?";
        if (hasFreshToday && typeof window.confirm === "function" && !window.confirm(message)) {
          event.preventDefault();
        }
      });
    });
  }

  function getGpuPriceChartEntries() {
    if (gpuPriceChartEntries.length) {
      return gpuPriceChartEntries;
    }

    document.querySelectorAll("[data-gpu-price-chart]").forEach(function (shell) {
      if (!(shell instanceof HTMLElement)) {
        return;
      }

      const viewport = shell.querySelector("[data-chart-viewport]");
      const svg = shell.querySelector("svg");
      const scrollbar = shell.querySelector("[data-chart-scrollbar]");
      const scrollbarInner = shell.querySelector("[data-chart-scrollbar-inner]");
      const note = shell.querySelector("[data-chart-filter-note]");
      const seed = parseJsonNode(shell.querySelector("[data-gpu-price-chart-seed]"));
      if (!(viewport instanceof HTMLElement) || !(svg instanceof SVGSVGElement) || !seed) {
        return;
      }

      gpuPriceChartEntries.push({
        shell: shell,
        viewport: viewport,
        svg: svg,
        scrollbar: scrollbar instanceof HTMLElement ? scrollbar : null,
        scrollbarInner: scrollbarInner instanceof HTMLElement ? scrollbarInner : null,
        note: note instanceof HTMLElement ? note : null,
        seed: seed,
        title: shell.getAttribute("data-chart-title") || String(seed.title || "GPU Price Index"),
        filterable: seed.filterable !== false,
        visiblePointLimit: Math.max(
          1,
          Number.parseInt(shell.getAttribute("data-chart-visible-limit") || String(GPU_PRICE_DEFAULT_VISIBLE_POINTS), 10) ||
            GPU_PRICE_DEFAULT_VISIBLE_POINTS
        ),
      });
    });

    return gpuPriceChartEntries;
  }

  function formatGpuPriceValue(value, axisMode) {
    const amount = Number(value || 0);
    const precision = axisMode ? (Math.abs(amount) >= 10 ? 0 : 1) : 2;
    return `$${amount.toFixed(precision).replace(".00", "").replace(".0", "")}/GPU/h`;
  }

  function buildFilteredGpuPricePoint(sourcePoint, family) {
    const series = Array.isArray(sourcePoint.series) ? sourcePoint.series : [];
    const filteredSeries = family
      ? series.filter(function (item) {
          return String(item.symbol || "").toUpperCase() === family;
        })
      : series.slice();

    return {
      label: String(sourcePoint.label || ""),
      pointLabel: String(sourcePoint.point_label || sourcePoint.pointLabel || sourcePoint.date || ""),
      date: String(sourcePoint.date || sourcePoint.point_at || ""),
      series: filteredSeries.map(function (item) {
        return {
          symbol: String(item.symbol || ""),
          label: String(item.label || item.symbol || ""),
          color: String(item.color || "#2752b8"),
          value: Number(item.value || 0),
          valueLabel: String(item.value_label || item.valueLabel || formatGpuPriceValue(item.value || 0, false)),
          secondaryLabel: String(item.secondary_label || item.secondaryLabel || ""),
        };
      }),
    };
  }

  function buildGpuPriceChartState(seed, family) {
    const sourcePoints = Array.isArray(seed.points) ? seed.points : [];
    const points = sourcePoints.map(function (point) {
      return buildFilteredGpuPricePoint(point, family);
    });
    const margin = {
      top: 52,
      right: 36,
      bottom: 92,
      left: 92,
    };
    const visiblePointLimit = Math.max(
      1,
      Number.parseInt(seed.visible_point_limit || seed.visiblePointLimit || GPU_PRICE_DEFAULT_VISIBLE_POINTS, 10) ||
        GPU_PRICE_DEFAULT_VISIBLE_POINTS
    );
    const visiblePointCount = Math.max(1, Math.min(points.length || 1, visiblePointLimit));
    const width = Math.max(
      GPU_PRICE_MIN_WIDTH,
      margin.left + margin.right + Math.max(0, points.length - 1) * GPU_PRICE_POINT_GAP + 60
    );
    const viewportWidth = Math.max(
      GPU_PRICE_MIN_WIDTH,
      margin.left + margin.right + Math.max(0, visiblePointCount - 1) * GPU_PRICE_POINT_GAP + 60
    );
    const height = GPU_PRICE_HEIGHT;
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const baselineY = height - margin.bottom;
    const step = points.length > 1 ? plotWidth / (points.length - 1) : 0;
    const values = points.reduce(function (result, point) {
      point.series.forEach(function (item) {
        if (Number.isFinite(Number(item.value))) {
          result.push(Number(item.value || 0));
        }
      });
      return result;
    }, []);
    const rawMinValue = values.length ? Math.min(...values) : 0;
    const rawMaxValue = values.length ? Math.max(...values) : 1;
    let minValue = rawMinValue > 0 ? rawMinValue * 0.94 : 0;
    let maxValue = rawMaxValue > 0 ? rawMaxValue * 1.06 : 1;
    if (maxValue - minValue < 0.5) {
      const midpoint = (maxValue + minValue) / 2;
      minValue = Math.max(0, midpoint - 0.25);
      maxValue = midpoint + 0.25;
    }
    const valueRange = Math.max(0.1, maxValue - minValue);
    const ticks = [0, 0.25, 0.5, 0.75, 1].map(function (ratio) {
      const value = minValue + valueRange * ratio;
      const y = baselineY - plotHeight * ratio;
      return {
        y: Number(y.toFixed(2)),
        label: formatGpuPriceValue(value, true),
      };
    });

    const plottedPoints = points.map(function (point, index) {
      const x = points.length === 1 ? margin.left + plotWidth / 2 : margin.left + index * step;
      const bandWidth = points.length > 1 ? Math.min(82, Math.max(58, step * 0.72)) : 82;
      const series = point.series.map(function (item) {
        const y = baselineY - (((Number(item.value || 0) - minValue) / valueRange) * plotHeight);
        return {
          symbol: item.symbol,
          label: item.label,
          color: item.color,
          value: item.value,
          valueLabel: item.valueLabel,
          secondaryLabel: item.secondaryLabel,
          x: Number(x.toFixed(2)),
          y: Number(y.toFixed(2)),
        };
      });
      return {
        label: point.label,
        pointLabel: point.pointLabel,
        date: point.date,
        x: Number(x.toFixed(2)),
        labelY: baselineY + 44,
        hoverLeft: Number((x - bandWidth / 2).toFixed(2)),
        hoverTop: margin.top - 14,
        hoverWidth: Number(bandWidth.toFixed(2)),
        hoverHeight: plotHeight + 30,
        series: series,
      };
    });

    const lineIndex = new Map();
    plottedPoints.forEach(function (point) {
      point.series.forEach(function (item) {
        const key = String(item.symbol || "");
        if (!lineIndex.has(key)) {
          lineIndex.set(key, {
            symbol: key,
            label: item.label,
            color: item.color,
            points: [],
          });
        }
        lineIndex.get(key).points.push(item);
      });
    });

    return {
      width: width,
      viewportWidth: viewportWidth,
      height: height,
      baselineY: baselineY,
      margin: margin,
      ticks: ticks,
      points: plottedPoints,
      lines: Array.from(lineIndex.values()).map(function (line) {
        return {
          symbol: line.symbol,
          label: line.label,
          color: line.color,
          points: line.points,
          path: buildSmoothCdnTrendPath(line.points),
        };
      }),
      isScrollable: points.length > visiblePointLimit,
      visiblePointLimit: visiblePointLimit,
    };
  }

  function buildGpuPriceChartMarkup(seed, state) {
    const axisLeft = state.margin.left - 12;
    const axisRight = state.width - state.margin.right + 6;
    if (!state.points.length) {
      const centerX = state.width / 2;
      const centerY = state.height / 2;
      const title = String(seed.empty_title || "No price index yet");
      const subtitle = String(seed.empty_subtitle || "This series will populate after a source exposes matching rows.");
      return (
        `<line class="stablecoin-chart-baseline" x1="${state.margin.left - 6}" y1="${state.baselineY}" x2="${axisRight}" y2="${state.baselineY}"></line>` +
        `<g class="gpu-price-empty-state">` +
        `<text class="gpu-price-empty-title" x="${centerX}" y="${centerY - 10}">${escapeHtml(title)}</text>` +
        `<text class="gpu-price-empty-subtitle" x="${centerX}" y="${centerY + 18}">${escapeHtml(subtitle)}</text>` +
        `</g>`
      );
    }
    const ticksMarkup = state.ticks
      .map(function (tick) {
        return (
          `<g class="stablecoin-chart-tick gpu-price-chart-tick">` +
          `<line class="stablecoin-chart-grid" x1="${state.margin.left - 6}" y1="${tick.y}" x2="${axisRight}" y2="${tick.y}"></line>` +
          `<text class="stablecoin-chart-axis" x="${axisLeft}" y="${tick.y + 4}">${escapeHtml(tick.label)}</text>` +
          `</g>`
        );
      })
      .join("");
    const baselineMarkup = `<line class="stablecoin-chart-baseline" x1="${state.margin.left - 6}" y1="${state.baselineY}" x2="${axisRight}" y2="${state.baselineY}"></line>`;
    const linesMarkup = state.lines
      .map(function (line) {
        const pointMarkup = line.points
          .map(function (point) {
            return `<circle class="gpu-price-chart-point-node" cx="${point.x}" cy="${point.y}" r="4.7" style="--gpu-price-color:${escapeHtml(line.color)}"></circle>`;
          })
          .join("");
        return (
          `<g class="gpu-price-chart-line-group" data-gpu-price-family="${escapeHtml(line.symbol)}">` +
          `<path class="gpu-price-chart-line" d="${escapeHtml(line.path)}" style="--gpu-price-color:${escapeHtml(line.color)}"></path>` +
          pointMarkup +
          `</g>`
        );
      })
      .join("");
    const columnsMarkup = state.points
      .map(function (point) {
        const pointSeriesJson = escapeHtml(JSON.stringify(point.series));
        return (
          `<g class="stablecoin-chart-bar gpu-price-chart-column" data-gpu-price-point data-point-label="${escapeHtml(point.pointLabel)}" data-point-series="${pointSeriesJson}" tabindex="0">` +
          `<rect class="stablecoin-chart-hover-band" x="${point.hoverLeft}" y="${point.hoverTop}" width="${point.hoverWidth}" height="${point.hoverHeight}" rx="16" ry="16"></rect>` +
          `<text class="stablecoin-chart-month gpu-price-chart-date" x="${point.x}" y="${point.labelY}">${escapeHtml(point.label)}</text>` +
          `<rect class="stablecoin-chart-hitbox" x="${point.hoverLeft}" y="${point.hoverTop}" width="${point.hoverWidth}" height="${point.hoverHeight}" rx="16" ry="16"></rect>` +
          `</g>`
        );
      })
      .join("");

    return `${ticksMarkup}${baselineMarkup}${linesMarkup}${columnsMarkup}`;
  }

  function renderGpuPriceChart(entry, family) {
    entry.seed.visible_point_limit = entry.visiblePointLimit;
    const activeFamily = family || "";
    const state = buildGpuPriceChartState(entry.seed, activeFamily);
    entry.svg.setAttribute("viewBox", `0 0 ${state.width} ${state.height}`);
    entry.svg.setAttribute(
      "aria-label",
      activeFamily ? `${entry.title} - ${activeFamily}` : String(entry.seed.title || entry.title || "")
    );
    entry.svg.innerHTML = buildGpuPriceChartMarkup(entry.seed, state);
    entry.svg.style.width = state.isScrollable ? `${state.width}px` : "100%";
    entry.svg.style.minWidth = `${state.isScrollable ? state.width : Math.min(state.width, state.viewportWidth)}px`;

    if (entry.viewport instanceof HTMLElement) {
      entry.viewport.style.maxWidth = state.isScrollable ? `${state.viewportWidth}px` : "100%";
      entry.viewport.scrollLeft = 0;
    }
    if (entry.scrollbar instanceof HTMLElement && entry.scrollbarInner instanceof HTMLElement) {
      entry.scrollbar.hidden = !state.isScrollable;
      entry.scrollbarInner.style.width = `${state.width}px`;
      entry.scrollbar.scrollLeft = 0;
    }

    entry.shell.classList.toggle("is-scrollable-x", state.isScrollable);
    entry.shell.setAttribute("data-active-gpu-family", activeFamily || "");

    if (entry.note instanceof HTMLElement) {
      let baseNote = String(entry.seed.filter_note || "").trim();
      if (!baseNote) {
        baseNote = activeFamily
          ? `Focused on ${activeFamily}. Click the same legend chip again to restore H and B card series.`
          : "Click a GPU family above to isolate one price series; B-card series are included when present.";
      }
      if (state.points.length < 2) {
        baseNote = "Only one daily snapshot is stored right now. More daily refreshes will draw the time-series curve.";
      }
      entry.note.textContent = state.isScrollable
        ? `${baseNote} Use the horizontal scrollbar to move along the stored date axis.`
        : baseNote;
    }

    if (state.isScrollable && entry.viewport instanceof HTMLElement) {
      window.requestAnimationFrame(function () {
        const targetScrollLeft = Math.max(0, state.width - entry.viewport.clientWidth);
        entry.viewport.scrollLeft = targetScrollLeft;
        syncGpuPriceScrollbarFromViewport(entry);
      });
      return;
    }

    window.requestAnimationFrame(function () {
      syncGpuPriceScrollbarFromViewport(entry);
    });
  }

  function syncGpuPriceScrollbarFromViewport(entry) {
    if (
      !(entry.viewport instanceof HTMLElement) ||
      !(entry.scrollbar instanceof HTMLElement) ||
      !(entry.scrollbarInner instanceof HTMLElement)
    ) {
      return;
    }
    const maxScrollLeft = Math.max(0, entry.viewport.scrollWidth - entry.viewport.clientWidth);
    const isActuallyScrollable = maxScrollLeft > 1;
    entry.scrollbar.hidden = !isActuallyScrollable;
    entry.scrollbarInner.style.width = `${entry.viewport.scrollWidth}px`;
    entry.scrollbar.scrollLeft = Math.round(Math.min(maxScrollLeft, entry.viewport.scrollLeft));
    entry.shell.classList.toggle("is-scrollable-x", isActuallyScrollable);
  }

  function setupGpuPriceScrollbars() {
    getGpuPriceChartEntries().forEach(function (entry) {
      if (
        !(entry.viewport instanceof HTMLElement) ||
        !(entry.scrollbar instanceof HTMLElement) ||
        !(entry.scrollbarInner instanceof HTMLElement)
      ) {
        return;
      }
      if (entry.shell.getAttribute("data-gpu-price-scroll-bound") === "true") {
        return;
      }
      entry.shell.setAttribute("data-gpu-price-scroll-bound", "true");

      let isSyncing = false;
      entry.viewport.addEventListener("scroll", function () {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        syncGpuPriceScrollbarFromViewport(entry);
        window.requestAnimationFrame(function () {
          isSyncing = false;
        });
      });
      entry.scrollbar.addEventListener("scroll", function () {
        if (isSyncing) {
          return;
        }
        isSyncing = true;
        entry.viewport.scrollLeft = entry.scrollbar.scrollLeft;
        window.requestAnimationFrame(function () {
          isSyncing = false;
        });
      });
      syncGpuPriceScrollbarFromViewport(entry);
    });
  }

  function updateGpuPriceLegendState() {
    document.querySelectorAll("[data-gpu-price-legend]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      const family = String(button.getAttribute("data-gpu-price-legend") || "").toUpperCase();
      const isActive = Boolean(activeGpuPriceFamily) && family === activeGpuPriceFamily;
      const isDimmed = Boolean(activeGpuPriceFamily) && family !== activeGpuPriceFamily;
      button.classList.toggle("is-active", isActive);
      button.classList.toggle("is-dimmed", isDimmed);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function renderAllGpuPriceCharts() {
    hideActiveGpuPriceTooltip();
    getGpuPriceChartEntries().forEach(function (entry) {
      renderGpuPriceChart(entry, entry.filterable ? activeGpuPriceFamily : "");
    });
    updateGpuPriceLegendState();
  }

  function setupGpuPriceLegendFilter() {
    const buttons = Array.from(document.querySelectorAll("[data-gpu-price-legend]"));
    if (!buttons.length) {
      return;
    }
    buttons.forEach(function (button) {
      if (!(button instanceof HTMLButtonElement) || button.getAttribute("data-gpu-legend-bound") === "true") {
        return;
      }
      button.setAttribute("data-gpu-legend-bound", "true");
      button.addEventListener("click", function (event) {
        event.preventDefault();
        const family = String(button.getAttribute("data-gpu-price-legend") || "").toUpperCase();
        activeGpuPriceFamily = activeGpuPriceFamily === family ? "" : family;
        renderAllGpuPriceCharts();
      });
    });
    updateGpuPriceLegendState();
  }

  function ensureGpuPriceTooltip() {
    let tooltip = document.querySelector("[data-gpu-price-tooltip]");
    if (tooltip instanceof HTMLElement) {
      return tooltip;
    }
    tooltip = document.createElement("div");
    tooltip.className = "cdn-trend-tooltip gpu-price-tooltip";
    tooltip.setAttribute("data-gpu-price-tooltip", "");
    tooltip.hidden = true;
    document.body.appendChild(tooltip);
    return tooltip;
  }

  function formatGpuPriceSeriesRows(series) {
    return series
      .slice()
      .sort(function (left, right) {
        return Number(right.value || 0) - Number(left.value || 0);
      })
      .map(function (item) {
        const color = escapeHtml(String(item.color || "#2752b8"));
        const label = escapeHtml(String(item.label || item.symbol || ""));
        const valueLabel = escapeHtml(String(item.valueLabel || item.value_label || ""));
        const secondaryLabel = escapeHtml(String(item.secondaryLabel || item.secondary_label || ""));
        const secondaryMarkup = secondaryLabel ? `<span>${secondaryLabel}</span>` : "";
        return (
          '<li class="cdn-trend-tooltip-row">' +
          `<span class="cdn-trend-tooltip-key"><span class="cdn-trend-tooltip-swatch" style="--cdn-provider-color:${color}"></span>${label}</span>` +
          `<strong>${valueLabel}</strong>` +
          secondaryMarkup +
          "</li>"
        );
      })
      .join("");
  }

  function findGpuPricePointNode(target) {
    if (!(target instanceof Element)) {
      return null;
    }
    return target.closest("[data-gpu-price-point]");
  }

  function setupGpuPriceHover() {
    const entries = getGpuPriceChartEntries();
    if (!entries.length) {
      return;
    }

    const tooltip = ensureGpuPriceTooltip();
    let activePoint = null;

    function hideTooltip() {
      if (tooltip instanceof HTMLElement) {
        tooltip.hidden = true;
        tooltip.classList.remove("is-visible");
      }
      if (activePoint instanceof SVGGElement) {
        activePoint.classList.remove("is-active");
      }
      activePoint = null;
    }

    function showTooltip(pointNode, x, y) {
      if (!(pointNode instanceof SVGGElement) || !(tooltip instanceof HTMLElement)) {
        return;
      }

      let series = [];
      try {
        series = JSON.parse(pointNode.getAttribute("data-point-series") || "[]");
      } catch (error) {
        series = [];
      }

      if (activePoint instanceof SVGGElement && activePoint !== pointNode) {
        activePoint.classList.remove("is-active");
      }
      activePoint = pointNode;
      activePoint.classList.add("is-active");

      const chartShell = pointNode.closest("[data-gpu-price-chart]");
      const chartTitle =
        chartShell instanceof HTMLElement ? String(chartShell.getAttribute("data-chart-title") || "GPU Price Index") : "GPU Price Index";
      tooltip.innerHTML =
        `<div class="cdn-trend-tooltip-head"><span>${escapeHtml(String(pointNode.getAttribute("data-point-label") || ""))}</span><strong>${escapeHtml(chartTitle)}</strong></div>` +
        `<ul class="cdn-trend-tooltip-list">${formatGpuPriceSeriesRows(series)}</ul>`;
      tooltip.hidden = false;
      tooltip.classList.add("is-visible");

      if (typeof x === "number" && typeof y === "number") {
        positionTooltip(tooltip, x, y);
        return;
      }

      const rect = pointNode.getBoundingClientRect();
      positionTooltip(tooltip, rect.left + rect.width / 2, rect.top + rect.height / 2);
    }

    entries.forEach(function (entry) {
      if (entry.shell.getAttribute("data-gpu-price-hover-bound") === "true") {
        return;
      }
      entry.shell.setAttribute("data-gpu-price-hover-bound", "true");

      entry.shell.addEventListener("pointermove", function (event) {
        const pointNode = findGpuPricePointNode(event.target);
        if (!(pointNode instanceof SVGGElement)) {
          hideTooltip();
          return;
        }
        showTooltip(pointNode, event.clientX, event.clientY);
      });
      entry.shell.addEventListener("pointerleave", hideTooltip);
      entry.shell.addEventListener("focusin", function (event) {
        const pointNode = findGpuPricePointNode(event.target);
        if (pointNode instanceof SVGGElement) {
          showTooltip(pointNode);
        }
      });
      entry.shell.addEventListener("focusout", function (event) {
        if (!(event.currentTarget instanceof HTMLElement)) {
          hideTooltip();
          return;
        }
        const nextTarget = event.relatedTarget;
        if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
          return;
        }
        hideTooltip();
      });
    });

    if (!gpuPriceWindowBound) {
      window.addEventListener("scroll", hideTooltip, true);
      window.addEventListener("resize", hideTooltip);
      gpuPriceWindowBound = true;
    }
    hideActiveGpuPriceTooltip = hideTooltip;
  }

  function initializeGpuPriceCharts() {
    resetGpuPriceChartEntries();
    getGpuPriceChartEntries();
    setupGpuPriceScrollbars();
    renderAllGpuPriceCharts();
    setupGpuPriceLegendFilter();
    setupGpuPriceHover();
    gpuPriceVisualsInitialized = true;
  }

  function scheduleGpuPriceVisualInitialization(force) {
    const shells = Array.from(document.querySelectorAll("[data-gpu-price-chart]")).filter(function (node) {
      return node instanceof HTMLElement;
    });
    if (!shells.length) {
      resetGpuPriceChartEntries();
      gpuPriceVisualsInitialized = false;
      gpuPriceVisualSignature = "";
      return;
    }
    const nextSignature = buildVisualSignature(shells);
    if (force || nextSignature !== gpuPriceVisualSignature) {
      resetGpuPriceChartEntries();
      gpuPriceVisualSignature = nextSignature;
      gpuPriceVisualsInitialized = false;
    }
    if (gpuPriceVisualsInitialized) {
      return;
    }
    queueWhenNearViewport(shells, function () {
      initializeGpuPriceCharts();
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    const poller = setupStatusPolling();
    const cdnPoller = setupCdnStatusPolling();
    setupRefresh(poller);
    setupCdnRefresh(cdnPoller);
    setupGpuPriceRefreshConfirm();
    setupCdnSiteDetails();
    setupTrendControls();
    scheduleStablecoinVisualInitialization();
    scheduleGpuPriceVisualInitialization();

    if (document.querySelector("[data-applovin-panel-shell]")) {
      initializeApplovinInteractiveState();
      return;
    }

    scheduleCdnTrendVisualInitialization();
  });
})();
