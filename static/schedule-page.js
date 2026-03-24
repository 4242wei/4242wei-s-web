(function () {
  var activeRequestToken = 0;

  function parseUrl(rawUrl) {
    var url = new URL(rawUrl, window.location.origin);
    url.hash = "";
    return url;
  }

  function isInteractiveTarget(target) {
    if (!(target instanceof Element)) {
      return false;
    }

    return Boolean(target.closest("a, button, input, textarea, select, summary, details, form, label"));
  }

  function isBoardSelectionUrl(rawUrl) {
    var url = parseUrl(rawUrl);
    if (url.origin !== window.location.origin || url.pathname !== "/schedule") {
      return false;
    }

    return (url.searchParams.get("view") || "board") === "board";
  }

  function initAutoSubmitForms(root) {
    root.querySelectorAll("form[data-auto-submit]").forEach(function (form) {
      if (!(form instanceof HTMLFormElement) || form.dataset.scheduleAutoSubmitBound === "true") {
        return;
      }

      form.dataset.scheduleAutoSubmitBound = "true";
      var fields = form.querySelectorAll("select, input[type='month'], input[type='date']");
      fields.forEach(function (field) {
        field.addEventListener("change", function () {
          form.requestSubmit();
        });
      });
    });
  }

  function syncScheduleForm(form) {
    var allDayToggle = form.querySelector("[data-schedule-all-day-toggle]");
    var timeRangeToggle = form.querySelector("[data-schedule-time-range-toggle]");
    var timeFields = form.querySelector("[data-schedule-time-fields]");

    if (!(timeRangeToggle instanceof HTMLInputElement) || !(timeFields instanceof HTMLElement)) {
      return;
    }

    var timeInputs = Array.from(timeFields.querySelectorAll("input[type='time']"));
    var isAllDay = allDayToggle instanceof HTMLInputElement && allDayToggle.checked;

    if (isAllDay) {
      timeRangeToggle.checked = false;
    }

    timeRangeToggle.disabled = isAllDay;

    var shouldShowTimeFields = !isAllDay && timeRangeToggle.checked;
    timeFields.hidden = !shouldShowTimeFields;

    timeInputs.forEach(function (input) {
      if (input instanceof HTMLInputElement) {
        input.disabled = !shouldShowTimeFields;
      }
    });
  }

  function initScheduleForms(root) {
    root.querySelectorAll("[data-schedule-form]").forEach(function (form) {
      if (!(form instanceof HTMLFormElement) || form.dataset.scheduleFormBound === "true") {
        return;
      }

      form.dataset.scheduleFormBound = "true";

      var allDayToggle = form.querySelector("[data-schedule-all-day-toggle]");
      var timeRangeToggle = form.querySelector("[data-schedule-time-range-toggle]");

      if (allDayToggle instanceof HTMLInputElement) {
        allDayToggle.addEventListener("change", function () {
          syncScheduleForm(form);
        });
      }

      if (timeRangeToggle instanceof HTMLInputElement) {
        timeRangeToggle.addEventListener("change", function () {
          syncScheduleForm(form);
        });
      }

      syncScheduleForm(form);
    });
  }

  function setLoadingState(isLoading) {
    var boardPanel = document.querySelector(".schedule-board-panel");
    var detailPanel = document.getElementById("selected-day-panel");
    [boardPanel, detailPanel].forEach(function (node) {
      if (!(node instanceof HTMLElement)) {
        return;
      }

      node.classList.toggle("is-loading", isLoading);
      node.setAttribute("aria-busy", isLoading ? "true" : "false");
    });
  }

  async function selectBoardState(rawUrl) {
    if (!isBoardSelectionUrl(rawUrl)) {
      window.location.assign(rawUrl);
      return;
    }

    var currentBoardPanel = document.querySelector(".schedule-board-panel");
    var currentDetailPanel = document.getElementById("selected-day-panel");
    if (!(currentBoardPanel instanceof HTMLElement) || !(currentDetailPanel instanceof HTMLElement)) {
      window.location.assign(rawUrl);
      return;
    }

    var targetUrl = parseUrl(rawUrl);
    var currentUrl = parseUrl(window.location.href);
    if (targetUrl.pathname === currentUrl.pathname && targetUrl.search === currentUrl.search) {
      return;
    }

    var requestToken = ++activeRequestToken;
    setLoadingState(true);

    try {
      var response = await fetch(targetUrl.toString(), {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error("Failed to load schedule board state");
      }

      var html = await response.text();
      if (requestToken !== activeRequestToken) {
        return;
      }

      var parsed = new DOMParser().parseFromString(html, "text/html");
      var nextBoardPanel = parsed.querySelector(".schedule-board-panel");
      var nextDetailPanel = parsed.getElementById("selected-day-panel");

      if (!(nextBoardPanel instanceof HTMLElement) || !(nextDetailPanel instanceof HTMLElement)) {
        throw new Error("Schedule board fragments missing");
      }

      var liveBoardPanel = document.querySelector(".schedule-board-panel");
      var liveDetailPanel = document.getElementById("selected-day-panel");
      if (!(liveBoardPanel instanceof HTMLElement) || !(liveDetailPanel instanceof HTMLElement)) {
        throw new Error("Schedule board fragments unavailable");
      }

      liveBoardPanel.replaceWith(nextBoardPanel);
      liveDetailPanel.replaceWith(nextDetailPanel);

      window.history.replaceState({ scheduleBoard: true }, "", targetUrl.pathname + targetUrl.search);

      initBoardInteractions(document);
      initScheduleForms(document);
      initAutoSubmitForms(document);
    } catch (error) {
      window.location.assign(rawUrl);
      return;
    } finally {
      if (requestToken === activeRequestToken) {
        setLoadingState(false);
      }
    }
  }

  function initBoardInteractions(root) {
    root.querySelectorAll(".schedule-board-day[data-day-url]").forEach(function (card) {
      if (!(card instanceof HTMLElement) || card.dataset.scheduleDayBound === "true") {
        return;
      }

      card.dataset.scheduleDayBound = "true";
      var dayUrl = card.dataset.dayUrl;
      if (!dayUrl) {
        return;
      }

      card.addEventListener("click", function (event) {
        if (isInteractiveTarget(event.target)) {
          return;
        }

        selectBoardState(dayUrl);
      });

      card.addEventListener("keydown", function (event) {
        if (event.key !== "Enter" && event.key !== " ") {
          return;
        }

        if (event.target !== card && isInteractiveTarget(event.target)) {
          return;
        }

        event.preventDefault();
        selectBoardState(dayUrl);
      });
    });

    root.querySelectorAll(".schedule-board-day-anchor, .schedule-board-item, .schedule-board-more").forEach(function (link) {
      if (!(link instanceof HTMLAnchorElement) || link.dataset.scheduleLinkBound === "true") {
        return;
      }

      link.dataset.scheduleLinkBound = "true";
      link.addEventListener("click", function (event) {
        if (!isBoardSelectionUrl(link.href)) {
          return;
        }

        event.preventDefault();
        event.stopPropagation();
        selectBoardState(link.href);
      });
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    initBoardInteractions(document);
    initScheduleForms(document);
    initAutoSubmitForms(document);
  });
})();
