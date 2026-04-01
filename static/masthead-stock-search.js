(function () {
  const RECENT_KEY = "masthead-stock-search-recent-v1";
  const RECENT_LIMIT = 6;

  function normalizeQuery(value) {
    return String(value || "").trim().toUpperCase();
  }

  function readRecentSymbols() {
    try {
      const raw = window.localStorage.getItem(RECENT_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed.map(normalizeQuery).filter(Boolean);
    } catch (error) {
      return [];
    }
  }

  function writeRecentSymbol(symbol) {
    const normalized = normalizeQuery(symbol);
    if (!normalized) {
      return;
    }

    const next = [normalized]
      .concat(readRecentSymbols().filter(function (item) {
        return item !== normalized;
      }))
      .slice(0, RECENT_LIMIT);

    try {
      window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch (error) {
      // Ignore storage failures and keep the jump behavior working.
    }
  }

  function parseOptions(seed) {
    if (!(seed instanceof HTMLScriptElement)) {
      return [];
    }

    try {
      const parsed = JSON.parse(seed.textContent || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      return [];
    }
  }

  function matchesQuery(option, query) {
    const normalizedQuery = normalizeQuery(query);
    if (!normalizedQuery) {
      return true;
    }

    const symbol = normalizeQuery(option.symbol);
    const displayName = String(option.display_name || "").trim().toUpperCase();
    return symbol.includes(normalizedQuery) || displayName.includes(normalizedQuery);
  }

  function sortMatches(options, query) {
    const normalizedQuery = normalizeQuery(query);
    return options
      .slice()
      .sort(function (left, right) {
        const leftSymbol = normalizeQuery(left.symbol);
        const rightSymbol = normalizeQuery(right.symbol);
        const leftStarts = leftSymbol.startsWith(normalizedQuery) ? 1 : 0;
        const rightStarts = rightSymbol.startsWith(normalizedQuery) ? 1 : 0;
        if (leftStarts !== rightStarts) {
          return rightStarts - leftStarts;
        }
        const leftFavorite = left.is_favorite ? 1 : 0;
        const rightFavorite = right.is_favorite ? 1 : 0;
        if (leftFavorite !== rightFavorite) {
          return rightFavorite - leftFavorite;
        }
        return leftSymbol.localeCompare(rightSymbol);
      });
  }

  function createItem(option, badgeLabel) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "masthead-stock-search-item";
    button.setAttribute("data-stock-jump-symbol", option.symbol);

    const copy = document.createElement("span");
    copy.className = "masthead-stock-search-item-copy";

    const symbol = document.createElement("span");
    symbol.className = "masthead-stock-search-item-symbol";
    symbol.textContent = option.symbol;

    const meta = document.createElement("span");
    meta.className = "masthead-stock-search-item-meta";
    meta.textContent = option.display_name && option.display_name !== option.symbol
      ? option.display_name
      : "点击后直接跳到个股页";

    copy.appendChild(symbol);
    copy.appendChild(meta);

    const badge = document.createElement("span");
    badge.className = "masthead-stock-search-item-badge";
    badge.textContent = badgeLabel;

    button.appendChild(copy);
    button.appendChild(badge);
    return button;
  }

  document.querySelectorAll("[data-stock-jump-search]").forEach(function (form) {
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const input = form.querySelector("[data-stock-jump-input]");
    const panel = form.querySelector("[data-stock-jump-panel]");
    const list = form.querySelector("[data-stock-jump-list]");
    const title = form.querySelector("[data-stock-jump-title]");
    const hint = form.querySelector("[data-stock-jump-hint]");
    const seed = form.querySelector("[data-stock-jump-options]");

    if (!(input instanceof HTMLInputElement) || !(panel instanceof HTMLElement) || !(list instanceof HTMLElement)) {
      return;
    }

    const options = parseOptions(seed);
    const optionMap = new Map(
      options.map(function (option) {
        return [normalizeQuery(option.symbol), option];
      })
    );

    function openPanel() {
      panel.hidden = false;
    }

    function closePanel() {
      panel.hidden = true;
    }

    function renderEmpty(message) {
      list.innerHTML = "";
      const empty = document.createElement("div");
      empty.className = "masthead-stock-search-empty";
      empty.textContent = message;
      list.appendChild(empty);
    }

    function renderRecent() {
      const recentOptions = readRecentSymbols()
        .map(function (symbol) {
          return optionMap.get(symbol) || null;
        })
        .filter(Boolean);

      list.innerHTML = "";
      if (title instanceof HTMLElement) {
        title.textContent = "最近查看";
      }
      if (hint instanceof HTMLElement) {
        hint.textContent = "点击即可回到最近输入过的个股页。";
      }

      if (!recentOptions.length) {
        renderEmpty("还没有最近搜索记录。输入股票代码后，这里会自动记住。");
        return;
      }

      recentOptions.forEach(function (option) {
        list.appendChild(createItem(option, option.is_favorite ? "自选" : "最近"));
      });
    }

    function renderMatches(query) {
      const matches = sortMatches(
        options.filter(function (option) {
          return matchesQuery(option, query);
        }),
        query
      ).slice(0, 8);

      list.innerHTML = "";
      if (title instanceof HTMLElement) {
        title.textContent = "匹配结果";
      }
      if (hint instanceof HTMLElement) {
        hint.textContent = "回车会优先跳转精确匹配；也可以直接点下面的股票。";
      }

      if (!matches.length) {
        renderEmpty("没有找到这个股票代码。你可以继续输入更完整的代码。");
        return;
      }

      matches.forEach(function (option) {
        list.appendChild(createItem(option, option.is_favorite ? "自选" : "跳转"));
      });
    }

    function renderPanel() {
      const query = normalizeQuery(input.value);
      if (query) {
        renderMatches(query);
      } else {
        renderRecent();
      }
    }

    function navigateTo(symbol) {
      const normalized = normalizeQuery(symbol);
      const option = optionMap.get(normalized);
      if (!option || !option.detail_url) {
        renderMatches(normalized);
        openPanel();
        input.focus();
        return;
      }

      writeRecentSymbol(normalized);
      window.location.assign(option.detail_url);
    }

    input.addEventListener("focus", function () {
      openPanel();
      renderPanel();
    });

    input.addEventListener("click", function () {
      openPanel();
      renderPanel();
    });

    input.addEventListener("input", function () {
      openPanel();
      renderPanel();
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const query = normalizeQuery(input.value);
      if (!query) {
        openPanel();
        renderRecent();
        return;
      }

      const exact = optionMap.get(query);
      if (exact) {
        navigateTo(exact.symbol);
        return;
      }

      const matches = sortMatches(
        options.filter(function (option) {
          return matchesQuery(option, query);
        }),
        query
      );
      if (matches.length === 1) {
        navigateTo(matches[0].symbol);
        return;
      }

      openPanel();
      renderMatches(query);
      input.focus();
    });

    list.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const button = target.closest("[data-stock-jump-symbol]");
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }

      navigateTo(button.getAttribute("data-stock-jump-symbol") || "");
    });

    document.addEventListener("click", function (event) {
      const target = event.target;
      if (target instanceof Node && form.contains(target)) {
        return;
      }
      closePanel();
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closePanel();
      }
    });
  });
})();
