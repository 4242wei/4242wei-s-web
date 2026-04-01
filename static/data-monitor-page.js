(function () {
  const CHART_MIN_WIDTH = 880;
  const CHART_HEIGHT = 468;
  const CHART_DEFAULT_VISIBLE_BARS = 15;
  const CHART_BAR_WIDTH = 44;
  const CHART_BAR_GAP = 18;
  const chartEntries = [];
  let activeLegendSymbol = "";
  let hideActiveChartTooltip = function () {};

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

  window.addEventListener("DOMContentLoaded", function () {
    const poller = setupStatusPolling();
    setupRefresh(poller);
    getChartEntries();
    setupChartScrollbars();
    renderAllCharts();
    setupLegendFilter();
    setupChartHover();
  });
})();
