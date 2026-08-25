(function () {
  "use strict";

  const bootstrapNode = document.querySelector("[data-expert-portfolio-bootstrap]");
  const root = document.querySelector("[data-expert-portfolio-root]");
  if (!bootstrapNode || !root) {
    return;
  }

  let bootstrap = { experts: [], readonly: false };
  try {
    bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  } catch (error) {
    console.error("专家组合初始化数据读取失败", error);
  }

  const expertsById = new Map((bootstrap.experts || []).map(function (expert) {
    return [String(expert.id), expert];
  }));
  const tableBody = document.querySelector("[data-portfolio-table-body]");
  const rows = tableBody ? Array.from(tableBody.querySelectorAll("[data-expert-id]")) : [];
  const searchInput = document.querySelector("[data-portfolio-search]");
  const visibleCount = document.querySelector("[data-portfolio-visible-count]");
  const emptyState = document.querySelector("[data-portfolio-empty]");
  const toast = document.querySelector("[data-portfolio-toast]");
  const readonly = bootstrap.readonly === true || root.dataset.readonly === "true";
  const statusTones = {
    "not-reviewed": "pending",
    scheduling: "info",
    completed: "success",
    "scheduling-followup": "purple",
    "followup-in-progress": "warning",
    "maybe-not": "pending",
  };
  const statusOrder = Object.keys(statusTones).reduce(function (result, key, index) {
    result[key] = index;
    return result;
  }, {});
  let activeFilter = { kind: "all", value: "" };
  let sortState = { key: "", direction: 1 };
  let parsedIntakeExperts = [];
  let intakeProviders = [];
  let toastTimer = null;
  let summaryPollTimer = null;
  const interviewDraftPrefix = "expert-interview-draft:v1:";
  const interviewDraftTtl = 24 * 60 * 60 * 1000;
  const interviewDraftTimers = new WeakMap();

  function showToast(message, isError) {
    if (!toast) {
      return;
    }
    toast.textContent = message || "已保存";
    toast.classList.toggle("is-error", Boolean(isError));
    toast.hidden = false;
    toast.classList.remove("is-visible");
    window.requestAnimationFrame(function () {
      toast.classList.add("is-visible");
    });
    if (toastTimer) {
      window.clearTimeout(toastTimer);
    }
    toastTimer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
      window.setTimeout(function () {
        toast.hidden = true;
      }, 180);
    }, 2200);
  }

  function normalize(value) {
    return String(value || "").trim().toLocaleLowerCase("zh-CN");
  }

  function rowMatches(row) {
    const query = normalize(searchInput ? searchInput.value : "");
    if (query && !normalize(row.dataset.search).includes(query)) {
      return false;
    }
    if (activeFilter.kind === "vendor") {
      return String(row.dataset.vendors || "").includes("|" + activeFilter.value + "|");
    }
    if (activeFilter.kind === "status") {
      return row.dataset.status === activeFilter.value;
    }
    if (activeFilter.kind === "category") {
      return row.dataset.category === activeFilter.value;
    }
    if (activeFilter.kind === "industry") {
      return row.dataset.industry === activeFilter.value;
    }
    if (activeFilter.kind === "region") {
      return row.dataset.region === activeFilter.value;
    }
    if (activeFilter.kind === "scale") {
      return row.dataset.scale === activeFilter.value;
    }
    if (activeFilter.kind === "needs-review") {
      return row.dataset.needsReview === "1";
    }
    if (activeFilter.kind === "multiple-interviews") {
      return row.dataset.multipleInterviews === "1";
    }
    if (activeFilter.kind === "duplicates") {
      return row.dataset.duplicate === "1";
    }
    return true;
  }

  function applyFilters() {
    let count = 0;
    rows.forEach(function (row) {
      const matches = rowMatches(row);
      row.hidden = !matches;
      if (matches) {
        count += 1;
      }
    });
    if (visibleCount) {
      visibleCount.textContent = String(count);
    }
    if (emptyState) {
      emptyState.hidden = count !== 0;
    }
  }

  function selectFilter(button) {
    document.querySelectorAll("[data-filter-kind]").forEach(function (item) {
      item.classList.toggle("is-active", item === button);
    });
    activeFilter = {
      kind: button.dataset.filterKind || "all",
      value: normalize(button.dataset.filterValue)
    };
    applyFilters();
  }

  document.querySelectorAll("[data-filter-kind]").forEach(function (button) {
    button.addEventListener("click", function () {
      selectFilter(button);
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
  }

  const clearButton = document.querySelector("[data-portfolio-clear]");
  if (clearButton) {
    clearButton.addEventListener("click", function () {
      if (searchInput) {
        searchInput.value = "";
      }
      const allButton = document.querySelector('[data-filter-kind="all"]');
      if (allButton) {
        selectFilter(allButton);
      } else {
        activeFilter = { kind: "all", value: "" };
        applyFilters();
      }
    });
  }

  function sortValue(row, key) {
    const rawValue = row.dataset["sort" + key.split("-").map(function (part) {
      return part.charAt(0).toUpperCase() + part.slice(1);
    }).join("")] || "";
    if (key === "status") {
      return statusOrder[rawValue] === undefined ? 999 : statusOrder[rawValue];
    }
    if (key === "vendor-index" || key === "record-id") {
      return rawValue.replace(/#/g, "").replace(/\d+/g, function (part) {
        return part.padStart(5, "0");
      });
    }
    return normalize(rawValue);
  }

  function sortRows(key) {
    if (!tableBody) {
      return;
    }
    if (sortState.key === key) {
      sortState.direction *= -1;
    } else {
      sortState = { key: key, direction: 1 };
    }
    rows.sort(function (left, right) {
      const leftValue = sortValue(left, key);
      const rightValue = sortValue(right, key);
      if (leftValue < rightValue) {
        return -1 * sortState.direction;
      }
      if (leftValue > rightValue) {
        return sortState.direction;
      }
      return normalize(left.dataset.sortName).localeCompare(normalize(right.dataset.sortName), "zh-CN");
    });
    rows.forEach(function (row) {
      tableBody.appendChild(row);
    });
    document.querySelectorAll("[data-sort-key]").forEach(function (button) {
      const isCurrent = button.dataset.sortKey === key;
      button.classList.toggle("is-active", isCurrent);
      button.dataset.direction = isCurrent ? (sortState.direction === 1 ? "asc" : "desc") : "";
    });
  }

  document.querySelectorAll("[data-sort-key]").forEach(function (button) {
    button.addEventListener("click", function () {
      sortRows(button.dataset.sortKey || "name");
    });
  });
  sortRows("record-id");

  function openDialog(dialog) {
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    if (!dialog.open) {
      dialog.showModal();
    }
    document.body.classList.add("has-expert-portfolio-dialog");
  }

  function setQuotaFullscreen(dialog, active) {
    if (!(dialog instanceof HTMLDialogElement) || dialog.id !== "expert-portfolio-quota-dialog") {
      return;
    }
    const enabled = Boolean(active);
    const button = dialog.querySelector("[data-quota-fullscreen]");
    const label = dialog.querySelector("[data-quota-fullscreen-label]");
    dialog.classList.toggle("is-fullscreen", enabled);
    if (button) {
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.setAttribute("title", enabled ? "恢复浮窗大小" : "展开为全屏浮窗");
    }
    if (label) {
      label.textContent = enabled ? "退出全屏" : "全屏";
    }
  }

  function closeDialog(dialog) {
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    if (dialog.id === "expert-portfolio-interviews-dialog") {
      flushOpenInterviewDraft(dialog);
    }
    setQuotaFullscreen(dialog, false);
    dialog.close();
    if (!document.querySelector("dialog[open]")) {
      document.body.classList.remove("has-expert-portfolio-dialog");
    }
  }

  document.querySelectorAll("[data-dialog-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      const dialog = document.getElementById(button.dataset.dialogOpen || "");
      openDialog(dialog);
    });
  });

  document.querySelectorAll("[data-quota-fullscreen]").forEach(function (button) {
    button.addEventListener("click", function () {
      const dialog = button.closest("dialog");
      if (dialog instanceof HTMLDialogElement) {
        setQuotaFullscreen(dialog, !dialog.classList.contains("is-fullscreen"));
      }
    });
  });

  document.querySelectorAll("dialog").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        if (dialog.id === "expert-portfolio-quota-dialog" && dialog.classList.contains("is-fullscreen")) {
          setQuotaFullscreen(dialog, false);
          return;
        }
        closeDialog(dialog);
      }
    });
    dialog.querySelectorAll("[data-dialog-close]").forEach(function (button) {
      button.addEventListener("click", function () {
        closeDialog(dialog);
      });
    });
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (dialog.id === "expert-portfolio-quota-dialog" && dialog.classList.contains("is-fullscreen")) {
        setQuotaFullscreen(dialog, false);
        return;
      }
      closeDialog(dialog);
    });
  });

  const calendarDialog = document.querySelector("[data-interview-calendar]");
  const calendarWeek = document.querySelector("[data-calendar-week]");
  const calendarRange = document.querySelector("[data-calendar-range]");
  const calendarSummary = document.querySelector("[data-calendar-summary]");
  const calendarEmpty = document.querySelector("[data-calendar-empty]");
  const calendarButtonSummary = document.querySelector("[data-calendar-button-summary]");
  const calendarSync = bootstrap.calendarSync && typeof bootstrap.calendarSync === "object" ? bootstrap.calendarSync : { events: [] };
  const calendarWeekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

  function twoDigits(value) {
    return String(value).padStart(2, "0");
  }

  function localDateKey(value) {
    return value.getFullYear() + "-" + twoDigits(value.getMonth() + 1) + "-" + twoDigits(value.getDate());
  }

  function startOfCalendarWeek(value) {
    const result = new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12);
    const weekday = result.getDay() || 7;
    result.setDate(result.getDate() - weekday + 1);
    return result;
  }

  function addCalendarDays(value, days) {
    const result = new Date(value.getFullYear(), value.getMonth(), value.getDate(), 12);
    result.setDate(result.getDate() + days);
    return result;
  }

  function interviewClock(value) {
    const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/);
    if (!match) {
      return null;
    }
    return {
      date: match[1] + "-" + match[2] + "-" + match[3],
      time: match[4] + ":" + match[5]
    };
  }

  function clockMinutes(clock) {
    if (!clock) {
      return null;
    }
    const parts = clock.time.split(":");
    return Number(parts[0]) * 60 + Number(parts[1]);
  }

  function displayRangeEndMinutes(interview, startMinutes) {
    const match = String(interview.display_time || "").match(/(\d{1,2})[:.](\d{2})\s*(am|pm)?\s*[–—~-]\s*(\d{1,2})[:.](\d{2})\s*(am|pm)?/i);
    if (!match) {
      return null;
    }
    let hour = Number(match[4]);
    const meridiem = String(match[6] || "").toLowerCase();
    if (meridiem === "pm" && hour < 12) {
      hour += 12;
    } else if (meridiem === "am" && hour === 12) {
      hour = 0;
    }
    let result = hour * 60 + Number(match[5]);
    if (result <= startMinutes) {
      result += 24 * 60;
    }
    return result;
  }

  function interviewTiming(interview, startClock) {
    const startMinutes = clockMinutes(startClock);
    const endedClock = interviewClock(interview.ended_at);
    let endMinutes = null;
    if (endedClock && endedClock.date === startClock.date) {
      endMinutes = clockMinutes(endedClock);
    }
    if (endMinutes === null) {
      endMinutes = displayRangeEndMinutes(interview, startMinutes);
    }
    if (endMinutes !== null && endMinutes > startMinutes) {
      return {
        startMinutes: startMinutes,
        endMinutes: endMinutes,
        timeLabel: startClock.time + "–" + twoDigits(Math.floor(endMinutes / 60) % 24) + ":" + twoDigits(endMinutes % 60),
        hasEnd: true
      };
    }
    return {
      startMinutes: startMinutes,
      endMinutes: startMinutes + 60,
      timeLabel: startClock.time + " 开始",
      hasEnd: false
    };
  }

  const calendarEvents = [];
  (bootstrap.experts || []).forEach(function (expert) {
    (expert.interviews || []).forEach(function (interview) {
      const startClock = interviewClock(interview.occurred_at);
      if (!startClock) {
        return;
      }
      const timing = interviewTiming(interview, startClock);
      calendarEvents.push({
        date: startClock.date,
        start: startClock.time,
        startMinutes: timing.startMinutes,
        endMinutes: timing.endMinutes,
        hasEnd: timing.hasEnd,
        timeLabel: timing.timeLabel,
        expertId: String(expert.id),
        name: expert.name || "未命名专家",
        company: expert.current_employer || expert.main_company || "公司待补充",
        status: interview.status || "planned",
        statusLabel: (interview.interview_sequence ? "第 " + interview.interview_sequence + " 次 · " : "") + (interview.status_label || "待安排"),
        sequence: Number(interview.interview_sequence || 0),
        source: "portfolio"
      });
    });
  });
  const portfolioEventKeys = new Set(calendarEvents.map(function (event) {
    return [event.expertId, event.date, event.start].join("|");
  }));
  (Array.isArray(calendarSync.events) ? calendarSync.events : []).forEach(function (item) {
    const startClock = interviewClock(item.start);
    if (!startClock) {
      return;
    }
    const timing = interviewTiming({ ended_at: item.end }, startClock);
    const expertId = String(item.expert_id || "");
    if (expertId && portfolioEventKeys.has([expertId, startClock.date, startClock.time].join("|"))) {
      return;
    }
    const isMatched = Boolean(expertId && expertsById.has(expertId));
    calendarEvents.push({
      date: startClock.date,
      start: startClock.time,
      startMinutes: timing.startMinutes,
      endMinutes: timing.endMinutes,
      hasEnd: timing.hasEnd,
      timeLabel: timing.timeLabel,
      expertId: isMatched ? expertId : "",
      name: item.expert_name || item.title || "Outlook 日历事件",
      company: item.expert_company || item.location || "专家待核对",
      status: isMatched ? "outlook" : "pending-review",
      statusLabel: isMatched
        ? (Number(item.interview_sequence || 0) ? "第 " + Number(item.interview_sequence) + " 次 · " : "") + (item.record_status === "linked_existing" ? "已有记录" : "Outlook 已核对")
        : "Outlook 待核对",
      sequence: Number(item.interview_sequence || 0),
      source: "outlook"
    });
  });
  calendarEvents.sort(function (left, right) {
    return (left.date + left.start + left.name).localeCompare(right.date + right.start + right.name);
  });

  const calendarToday = new Date();
  let calendarWeekStart = startOfCalendarWeek(calendarToday);
  const calendarStartHour = 7;
  const calendarEndHour = 24;
  const calendarHourHeight = 64;

  function calendarEventsForWeek(weekStart) {
    const first = localDateKey(weekStart);
    const last = localDateKey(addCalendarDays(weekStart, 6));
    return calendarEvents.filter(function (event) {
      return event.date >= first && event.date <= last;
    });
  }

  function formatCalendarRange(weekStart) {
    const weekEnd = addCalendarDays(weekStart, 6);
    if (weekStart.getFullYear() !== weekEnd.getFullYear()) {
      return weekStart.getFullYear() + "年" + (weekStart.getMonth() + 1) + "月" + weekStart.getDate() + "日–" + weekEnd.getFullYear() + "年" + (weekEnd.getMonth() + 1) + "月" + weekEnd.getDate() + "日";
    }
    if (weekStart.getMonth() !== weekEnd.getMonth()) {
      return weekStart.getFullYear() + "年" + (weekStart.getMonth() + 1) + "月" + weekStart.getDate() + "日–" + (weekEnd.getMonth() + 1) + "月" + weekEnd.getDate() + "日";
    }
    return weekStart.getFullYear() + "年" + (weekStart.getMonth() + 1) + "月" + weekStart.getDate() + "日–" + weekEnd.getDate() + "日";
  }

  function makeCalendarEvent(event) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "expert-portfolio-calendar-event is-" + event.status;
    button.classList.toggle("is-compact", event.endMinutes - event.startMinutes <= 60);
    button.dataset.calendarExpert = event.expertId;
    button.setAttribute("aria-label", event.timeLabel + "，" + event.name + "，" + event.company + "，" + event.statusLabel);
    const time = document.createElement("span");
    time.className = "expert-portfolio-calendar-event-time";
    time.textContent = event.timeLabel;
    const name = document.createElement("strong");
    name.textContent = event.name;
    const company = document.createElement("span");
    company.className = "expert-portfolio-calendar-event-company";
    company.textContent = event.company;
    const status = document.createElement("small");
    status.textContent = event.statusLabel;
    button.append(time, name, company, status);
    button.addEventListener("click", function () {
      if (!event.expertId) {
        showToast("这条 Outlook 日程尚未匹配到专家，请先核对专家姓名或公司。", true);
        return;
      }
      closeDialog(calendarDialog);
      window.requestAnimationFrame(function () {
        openInterviews(event.expertId, { returnToCalendar: true });
      });
    });
    return button;
  }

  function layoutCalendarEvents(events) {
    const sorted = events.slice().sort(function (left, right) {
      return left.startMinutes - right.startMinutes || left.endMinutes - right.endMinutes;
    });
    const groups = [];
    let currentGroup = [];
    let groupEnd = -1;
    sorted.forEach(function (event) {
      if (currentGroup.length && event.startMinutes >= groupEnd) {
        groups.push(currentGroup);
        currentGroup = [];
        groupEnd = -1;
      }
      currentGroup.push(event);
      groupEnd = Math.max(groupEnd, event.endMinutes);
    });
    if (currentGroup.length) {
      groups.push(currentGroup);
    }
    groups.forEach(function (group) {
      const laneEnds = [];
      group.forEach(function (event) {
        let lane = laneEnds.findIndex(function (end) { return end <= event.startMinutes; });
        if (lane < 0) {
          lane = laneEnds.length;
        }
        laneEnds[lane] = event.endMinutes;
        event.calendarLane = lane;
      });
      group.forEach(function (event) {
        event.calendarLanes = laneEnds.length;
      });
    });
    return sorted;
  }

  function makeCalendarDayHeader(date, index, todayKey) {
    const header = document.createElement("header");
    header.className = "expert-portfolio-calendar-day-head";
    header.style.gridColumn = String(index + 2);
    header.classList.toggle("is-today", localDateKey(date) === todayKey);
    const weekday = document.createElement("span");
    weekday.textContent = calendarWeekdays[index];
    const dayNumber = document.createElement("strong");
    dayNumber.textContent = String(date.getDate());
    header.append(weekday, dayNumber);
    return header;
  }

  function makeCalendarTimeRail(totalHeight) {
    const rail = document.createElement("div");
    rail.className = "expert-portfolio-calendar-time-rail";
    rail.style.height = totalHeight + "px";
    for (let hour = calendarStartHour; hour <= calendarEndHour; hour += 1) {
      const label = document.createElement("span");
      label.textContent = twoDigits(hour) + ":00";
      label.style.top = ((hour - calendarStartHour) * calendarHourHeight) + "px";
      rail.appendChild(label);
    }
    return rail;
  }

  function renderInterviewCalendar() {
    if (!calendarWeek) {
      return;
    }
    const weekEvents = calendarEventsForWeek(calendarWeekStart);
    calendarWeek.replaceChildren();
    const totalHeight = (calendarEndHour - calendarStartHour) * calendarHourHeight;
    calendarWeek.style.setProperty("--calendar-hour-height", calendarHourHeight + "px");
    const corner = document.createElement("div");
    corner.className = "expert-portfolio-calendar-corner";
    corner.textContent = "时间";
    calendarWeek.appendChild(corner);
    const todayKey = localDateKey(calendarToday);
    for (let index = 0; index < 7; index += 1) {
      calendarWeek.appendChild(makeCalendarDayHeader(addCalendarDays(calendarWeekStart, index), index, todayKey));
    }
    calendarWeek.appendChild(makeCalendarTimeRail(totalHeight));
    for (let index = 0; index < 7; index += 1) {
      const date = addCalendarDays(calendarWeekStart, index);
      const dateKey = localDateKey(date);
      const day = document.createElement("section");
      day.className = "expert-portfolio-calendar-day-track";
      day.classList.toggle("is-today", dateKey === todayKey);
      day.style.gridColumn = String(index + 2);
      day.style.height = totalHeight + "px";
      day.setAttribute("role", "gridcell");
      const dayEvents = weekEvents.filter(function (event) { return event.date === dateKey; });
      layoutCalendarEvents(dayEvents).forEach(function (event) {
        const visibleStart = Math.max(event.startMinutes, calendarStartHour * 60);
        const visibleEnd = Math.min(event.endMinutes, calendarEndHour * 60);
        if (visibleEnd <= visibleStart) {
          return;
        }
        const eventNode = makeCalendarEvent(event);
        eventNode.style.top = (((visibleStart - calendarStartHour * 60) / 60) * calendarHourHeight + 2) + "px";
        eventNode.style.height = Math.max(38, ((visibleEnd - visibleStart) / 60) * calendarHourHeight - 4) + "px";
        const lane = event.calendarLane || 0;
        const lanes = event.calendarLanes || 1;
        const laneWidth = 100 / lanes;
        eventNode.style.left = "calc(" + (lane * laneWidth) + "% + 5px)";
        eventNode.style.width = "calc(" + laneWidth + "% - 8px)";
        day.appendChild(eventNode);
      });
      if (dateKey === todayKey) {
        const nowMinutes = calendarToday.getHours() * 60 + calendarToday.getMinutes();
        if (nowMinutes >= calendarStartHour * 60 && nowMinutes <= calendarEndHour * 60) {
          const currentLine = document.createElement("span");
          currentLine.className = "expert-portfolio-calendar-now-line";
          currentLine.style.top = (((nowMinutes - calendarStartHour * 60) / 60) * calendarHourHeight) + "px";
          day.appendChild(currentLine);
        }
      }
      calendarWeek.appendChild(day);
    }
    if (calendarRange) {
      calendarRange.textContent = formatCalendarRange(calendarWeekStart);
    }
    if (calendarSummary) {
      calendarSummary.textContent = weekEvents.length ? "共 " + weekEvents.length + " 场访谈" : "本周无安排";
    }
    if (calendarEmpty) {
      calendarEmpty.hidden = weekEvents.length !== 0;
    }
    const calendarScroll = document.querySelector(".expert-portfolio-calendar-scroll");
    if (calendarScroll) {
      const earliest = weekEvents.length ? Math.min.apply(null, weekEvents.map(function (event) { return event.startMinutes; })) : calendarStartHour * 60;
      window.requestAnimationFrame(function () {
        calendarScroll.scrollTop = Math.max(0, ((earliest - calendarStartHour * 60 - 60) / 60) * calendarHourHeight);
      });
    }
  }

  if (calendarWeek) {
    const thisWeekEvents = calendarEventsForWeek(startOfCalendarWeek(calendarToday));
    if (calendarButtonSummary) {
      calendarButtonSummary.textContent = thisWeekEvents.length ? "本周 " + thisWeekEvents.length + " 场" : "本周暂无安排";
    }
    renderInterviewCalendar();
    const previousButton = document.querySelector("[data-calendar-previous]");
    const nextButton = document.querySelector("[data-calendar-next]");
    const currentButton = document.querySelector("[data-calendar-current]");
    if (previousButton) {
      previousButton.addEventListener("click", function () {
        calendarWeekStart = addCalendarDays(calendarWeekStart, -7);
        renderInterviewCalendar();
      });
    }
    if (nextButton) {
      nextButton.addEventListener("click", function () {
        calendarWeekStart = addCalendarDays(calendarWeekStart, 7);
        renderInterviewCalendar();
      });
    }
    if (currentButton) {
      currentButton.addEventListener("click", function () {
        calendarWeekStart = startOfCalendarWeek(calendarToday);
        renderInterviewCalendar();
      });
    }
  }

  const calendarSyncToggle = document.querySelector("[data-calendar-sync-toggle]");
  const calendarSyncPanel = document.querySelector("[data-calendar-sync-panel]");
  const calendarSyncStatus = document.querySelector("[data-calendar-sync-status]");

  function setCalendarSyncBusy(button, busy, label) {
    if (!(button instanceof HTMLButtonElement)) {
      return;
    }
    if (!button.dataset.idleLabel) {
      button.dataset.idleLabel = button.textContent || "";
    }
    button.disabled = busy;
    button.textContent = busy ? label : button.dataset.idleLabel;
  }

  async function calendarSyncRequest(url, options) {
    const response = await fetch(url, Object.assign({ headers: { "Accept": "application/json" } }, options || {}));
    const payload = await response.json().catch(function () { return {}; });
    if (!response.ok || payload.ok !== true) {
      throw new Error(payload.message || "日历同步失败，原有日程没有变化。");
    }
    return payload;
  }

  function pollCalendarSync(attempts) {
    let remaining = attempts;
    const check = async function () {
      try {
        const payload = await calendarSyncRequest("/expert-portfolio/calendar-sync/status");
        if (calendarSyncStatus) {
          calendarSyncStatus.textContent = payload.message || "正在同步";
        }
        if (payload.status === "ready") {
          window.location.reload();
          return;
        }
      } catch (error) {
        return;
      }
      remaining -= 1;
      if (remaining > 0) {
        window.setTimeout(check, 2000);
      }
    };
    window.setTimeout(check, 800);
  }

  if (calendarSyncToggle && calendarSyncPanel) {
    calendarSyncToggle.addEventListener("click", function () {
      calendarSyncPanel.hidden = !calendarSyncPanel.hidden;
      calendarSyncToggle.setAttribute("aria-expanded", calendarSyncPanel.hidden ? "false" : "true");
    });
  }

  const calendarConfigureForm = document.querySelector("[data-calendar-sync-configure]");
  if (calendarConfigureForm instanceof HTMLFormElement) {
    calendarConfigureForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const button = calendarConfigureForm.querySelector("button[type='submit']");
      setCalendarSyncBusy(button, true, "正在验证…");
      try {
        const formData = new FormData(calendarConfigureForm);
        const payload = await calendarSyncRequest("/expert-portfolio/calendar-sync/configure", {
          method: "POST",
          headers: { "Accept": "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ ics_url: formData.get("ics_url") || "" })
        });
        calendarConfigureForm.reset();
        if (calendarSyncStatus) {
          calendarSyncStatus.textContent = payload.message;
        }
        showToast(payload.message, false);
        pollCalendarSync(18);
      } catch (error) {
        showToast(error.message || "日历地址保存失败。", true);
      } finally {
        setCalendarSyncBusy(button, false, "");
      }
    });
  }

  const calendarImportForm = document.querySelector("[data-calendar-sync-import]");
  if (calendarImportForm instanceof HTMLFormElement) {
    calendarImportForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const button = calendarImportForm.querySelector("button[type='submit']");
      setCalendarSyncBusy(button, true, "正在读取…");
      try {
        const payload = await calendarSyncRequest("/expert-portfolio/calendar-sync/import", {
          method: "POST",
          body: new FormData(calendarImportForm)
        });
        showToast(payload.message + "（" + payload.event_count + " 条）", false);
        window.setTimeout(function () { window.location.reload(); }, 500);
      } catch (error) {
        showToast(error.message || "日历文件读取失败。", true);
      } finally {
        setCalendarSyncBusy(button, false, "");
      }
    });
  }

  const calendarRefreshButton = document.querySelector("[data-calendar-sync-refresh]");
  if (calendarRefreshButton instanceof HTMLButtonElement) {
    calendarRefreshButton.addEventListener("click", async function () {
      setCalendarSyncBusy(calendarRefreshButton, true, "正在同步…");
      try {
        const payload = await calendarSyncRequest("/expert-portfolio/calendar-sync/refresh", { method: "POST" });
        showToast(payload.message, false);
        pollCalendarSync(18);
      } catch (error) {
        showToast(error.message || "日历同步失败。", true);
        setCalendarSyncBusy(calendarRefreshButton, false, "");
      }
    });
  }

  const linkScanRefreshButton = document.querySelector("[data-link-scan-refresh]");
  const linkScanStatus = document.querySelector("[data-link-scan-status]");
  if (linkScanRefreshButton instanceof HTMLButtonElement) {
    linkScanRefreshButton.addEventListener("click", async function () {
      setCalendarSyncBusy(linkScanRefreshButton, true, "正在核对…");
      try {
        const payload = await calendarSyncRequest("/expert-portfolio/link-scan/refresh", { method: "POST" });
        if (linkScanStatus) {
          linkScanStatus.textContent = payload.message || "正在后台核对语音转录关联。";
        }
        showToast(payload.message || "正在核对语音转录关联");
      } catch (error) {
        showToast(error.message || "转录关联核对失败", true);
      } finally {
        setCalendarSyncBusy(linkScanRefreshButton, false, "");
      }
    });
  }

  function fillInput(form, name, value) {
    const field = form.elements.namedItem(name);
    if (field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement) {
      field.value = value === null || value === undefined ? "" : String(value);
    }
  }

  function vendorIndexText(value) {
    return Object.entries(value || {}).map(function (entry) {
      return entry[0] + ": " + entry[1];
    }).join(", ");
  }

  function jobHistoryText(value) {
    return (value || []).map(function (job) {
      return [job.title || "", job.company || "", job.dates || ""].join(" | ").replace(/(?:\s*\|\s*)+$/, "");
    }).join("\n");
  }

  function appendTextBlock(parent, label, value) {
    if (!value) {
      return;
    }
    const block = document.createElement("div");
    block.className = "expert-portfolio-interview-copy";
    const heading = document.createElement("strong");
    heading.textContent = label;
    const copy = document.createElement("p");
    copy.textContent = value;
    block.append(heading, copy);
    parent.appendChild(block);
  }

  function makeInterviewField(label, key, value, kind, options) {
    const wrapper = document.createElement("label");
    wrapper.className = "form-field";
    const caption = document.createElement("span");
    caption.className = "field-label";
    caption.textContent = label;
    let field;
    if (kind === "textarea") {
      field = document.createElement("textarea");
      field.rows = 3;
    } else if (kind === "select") {
      field = document.createElement("select");
      (options || []).forEach(function (option) {
        const node = document.createElement("option");
        node.value = option.value;
        node.textContent = option.label;
        field.appendChild(node);
      });
    } else {
      field = document.createElement("input");
      field.type = kind || "text";
    }
    field.dataset.interviewField = key;
    field.value = value || "";
    wrapper.append(caption, field);
    return wrapper;
  }

  function splitInterviewDateTime(value) {
    const match = String(value || "").match(/^(\d{4}-\d{2}-\d{2})(?:T|\s)(\d{2}:\d{2})/);
    return match ? { date: match[1], time: match[2] } : { date: "", time: "" };
  }

  function normalizeInterviewTime(value) {
    const compact = String(value || "").trim().replace(/[.：]/g, ":");
    let match = compact.match(/^(\d{1,2}):(\d{1,2})$/);
    if (!match) {
      match = compact.match(/^(\d{1,2})(\d{2})$/);
    }
    if (!match && /^\d{1,2}$/.test(compact)) {
      match = [compact, compact, "0"];
    }
    if (!match) {
      return "";
    }
    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      return "";
    }
    return twoDigits(hour) + ":" + twoDigits(minute);
  }

  function syncInterviewDateTime(container, key) {
    const hidden = container.querySelector('[data-interview-field="' + key + '"]');
    const date = container.querySelector('[data-interview-date-part="' + key + '"]');
    const time = container.querySelector('[data-interview-time-part="' + key + '"]');
    if (!hidden || !date || !time) {
      return;
    }
    const normalizedTime = normalizeInterviewTime(time.value);
    hidden.value = date.value && normalizedTime ? date.value + "T" + normalizedTime : "";
  }

  function setInterviewDateTime(container, key, value) {
    const parts = splitInterviewDateTime(value);
    const date = container.querySelector('[data-interview-date-part="' + key + '"]');
    const time = container.querySelector('[data-interview-time-part="' + key + '"]');
    if (date) {
      date.value = parts.date;
    }
    if (time) {
      time.value = parts.time;
    }
    syncInterviewDateTime(container, key);
  }

  function initializeInterviewDateTime(container) {
    container.querySelectorAll("[data-interview-datetime]").forEach(function (wrapper) {
      const key = wrapper.dataset.interviewDatetime || "";
      const hidden = wrapper.querySelector('[data-interview-field="' + key + '"]');
      setInterviewDateTime(container, key, hidden ? hidden.value : "");
      const date = wrapper.querySelector('[data-interview-date-part="' + key + '"]');
      const time = wrapper.querySelector('[data-interview-time-part="' + key + '"]');
      [date, time].forEach(function (field) {
        if (!field || field.dataset.datetimeReady === "1") {
          return;
        }
        field.dataset.datetimeReady = "1";
        field.addEventListener("input", function () {
          syncInterviewDateTime(container, key);
        });
      });
      if (time && time.dataset.timeBlurReady !== "1") {
        time.dataset.timeBlurReady = "1";
        time.addEventListener("blur", function () {
          const normalized = normalizeInterviewTime(time.value);
          if (normalized) {
            time.value = normalized;
          }
          syncInterviewDateTime(container, key);
        });
      }
    });
  }

  function makeInterviewDateTimeField(label, key, value) {
    const wrapper = document.createElement("div");
    wrapper.className = "form-field expert-interview-datetime-field";
    wrapper.dataset.interviewDatetime = key;
    const caption = document.createElement("span");
    caption.className = "field-label";
    caption.textContent = label;
    const parts = document.createElement("div");
    parts.className = "expert-interview-datetime-parts";
    const date = document.createElement("input");
    date.type = "date";
    date.dataset.interviewDatePart = key;
    date.setAttribute("aria-label", label + "日期");
    const time = document.createElement("input");
    time.type = "text";
    time.inputMode = "numeric";
    time.maxLength = 5;
    time.placeholder = key === "ended_at" ? "23:00" : "22:00";
    time.setAttribute("list", "expert-interview-time-options");
    time.dataset.interviewTimePart = key;
    time.setAttribute("aria-label", label + "时间");
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.dataset.interviewField = key;
    hidden.value = value || "";
    parts.append(date, time);
    wrapper.append(caption, parts, hidden);
    return wrapper;
  }

  function setInterviewDuration(container, minutes) {
    syncInterviewDateTime(container, "occurred_at");
    const start = container.querySelector('[data-interview-field="occurred_at"]');
    const startParts = splitInterviewDateTime(start ? start.value : "");
    if (!startParts.date || !startParts.time) {
      showToast("请先填写开始日期和时间。", true);
      return;
    }
    const startDate = new Date(startParts.date + "T" + startParts.time + ":00");
    if (Number.isNaN(startDate.getTime())) {
      showToast("开始时间格式不正确。", true);
      return;
    }
    startDate.setMinutes(startDate.getMinutes() + Number(minutes || 60));
    setInterviewDateTime(
      container,
      "ended_at",
      localDateKey(startDate) + "T" + twoDigits(startDate.getHours()) + ":" + twoDigits(startDate.getMinutes())
    );
    container.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function makeInterviewDurationActions() {
    const actions = document.createElement("div");
    actions.className = "expert-interview-duration-actions expert-portfolio-span-2";
    actions.dataset.interviewDurationActions = "";
    const caption = document.createElement("span");
    caption.textContent = "按开始时间快速设置结束：";
    actions.appendChild(caption);
    [[30, "+30 分钟"], [60, "+1 小时"], [90, "+1.5 小时"]].forEach(function (item) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.interviewDuration = String(item[0]);
      button.textContent = item[1];
      actions.appendChild(button);
    });
    return actions;
  }

  function interviewStatusOptions() {
    return [
      { value: "planned", label: "待安排" },
      { value: "scheduled", label: "已安排" },
      { value: "completed", label: "已完成" },
      { value: "cancelled", label: "已取消" }
    ];
  }

  function transcriptionQualityOptions() {
    return [
      { value: "needs-review", label: "需与音频核对" },
      { value: "reviewed", label: "已核对" },
      { value: "not-applicable", label: "无转录" }
    ];
  }

  function quotaStatusOptions() {
    return [
      { value: "", label: "自动判断" },
      { value: "completed", label: "已完成访谈" },
      { value: "scheduled", label: "已排期待访" },
      { value: "excluded", label: "不计入（失败/取消）" }
    ];
  }

  function transcriptOptions(selectedId) {
    const options = [{ value: "", label: "暂不关联" }];
    (bootstrap.transcripts || []).forEach(function (item) {
      options.push({ value: String(item.id), label: item.label || item.title || item.id });
    });
    if (selectedId && !options.some(function (item) { return item.value === selectedId; })) {
      options.push({ value: selectedId, label: "已关联的转录（当前不可用）" });
    }
    return options;
  }

  function summaryEndpoint(expertId, interviewId, suffix) {
    return "/expert-portfolio/experts/" + encodeURIComponent(expertId) +
      "/interviews/" + encodeURIComponent(interviewId) + "/summary" + (suffix || "");
  }

  function clearSummaryPoll() {
    if (summaryPollTimer) {
      window.clearTimeout(summaryPollTimer);
      summaryPollTimer = null;
    }
  }

  function setSummaryState(title, message, tone) {
    const state = document.querySelector("[data-summary-state]");
    const titleNode = document.querySelector("[data-summary-state-title]");
    const messageNode = document.querySelector("[data-summary-state-message]");
    if (state) {
      state.hidden = false;
      state.dataset.tone = tone || "info";
    }
    if (titleNode) {
      titleNode.textContent = title || "摘要状态";
    }
    if (messageNode) {
      messageNode.textContent = message || "";
    }
  }

  function renderSummaryPayload(payload) {
    const dialog = document.getElementById("expert-interview-summary-dialog");
    const state = document.querySelector("[data-summary-state]");
    const content = document.querySelector("[data-summary-content]");
    const overview = document.querySelector("[data-summary-overview]");
    const conclusions = document.querySelector("[data-summary-conclusions]");
    const count = document.querySelector("[data-summary-count]");
    const followupsSection = document.querySelector("[data-summary-followups-section]");
    const followups = document.querySelector("[data-summary-followups]");
    const meta = document.querySelector("[data-summary-meta]");
    const generateButton = document.querySelector("[data-summary-generate]");
    const summary = payload && payload.summary ? payload.summary : {};
    const items = Array.isArray(summary.conclusions) ? summary.conclusions : [];
    const status = String(payload && payload.status || "not-generated");
    const hasSummary = Boolean(summary.overview || items.length);

    if (conclusions) {
      conclusions.replaceChildren();
      items.forEach(function (item, index) {
        const card = document.createElement("article");
        card.className = "expert-interview-summary-conclusion";
        const head = document.createElement("div");
        const number = document.createElement("span");
        number.textContent = String(index + 1).padStart(2, "0");
        const title = document.createElement("h4");
        title.textContent = item.title || "访谈结论";
        head.append(number, title);
        const conclusion = document.createElement("p");
        conclusion.className = "expert-interview-summary-finding";
        conclusion.textContent = item.conclusion || "";
        card.append(head, conclusion);
        appendTextBlock(card, "转录依据", item.evidence);
        appendTextBlock(card, "限制与待核对", item.uncertainty);
        appendTextBlock(card, "位置参考", item.source_ref);
        conclusions.appendChild(card);
      });
    }
    if (count) {
      count.textContent = String(items.length);
    }
    if (overview) {
      overview.textContent = summary.overview || "";
    }
    if (followups) {
      followups.replaceChildren();
      (Array.isArray(summary.follow_ups) ? summary.follow_ups : []).forEach(function (item) {
        const node = document.createElement("li");
        node.textContent = item;
        followups.appendChild(node);
      });
    }
    if (followupsSection) {
      followupsSection.hidden = !(Array.isArray(summary.follow_ups) && summary.follow_ups.length);
    }
    if (content) {
      content.hidden = !hasSummary;
    }

    if (status === "ready") {
      if (state) {
        state.hidden = true;
      }
    } else if (status === "stale") {
      setSummaryState("摘要需要更新", payload.message, "warning");
    } else if (status === "queued" || status === "generating") {
      setSummaryState("后台生成中", payload.message, "loading");
    } else if (status === "failed" || status === "interrupted") {
      setSummaryState("摘要尚未完成", payload.message, "error");
    } else {
      setSummaryState("暂无摘要", payload.message, "info");
    }

    if (meta) {
      const parts = [];
      if (summary.generated_at) {
        parts.push("生成于 " + summary.generated_at.replace("T", " ").slice(0, 16));
      }
      if (summary.provider_label || summary.model) {
        parts.push([summary.provider_label, summary.model].filter(Boolean).join(" · "));
      }
      meta.textContent = parts.join(" ｜ ") || "摘要按需从关联转录生成";
    }
    if (generateButton) {
      generateButton.hidden = readonly || !(payload && payload.can_generate);
      generateButton.disabled = status === "queued" || status === "generating";
      generateButton.textContent = hasSummary ? "重新生成" : "生成摘要";
    }

    clearSummaryPoll();
    if ((status === "queued" || status === "generating") && dialog instanceof HTMLDialogElement && dialog.open) {
      const expertId = dialog.dataset.expertId || "";
      const interviewId = dialog.dataset.interviewId || "";
      summaryPollTimer = window.setTimeout(function () {
        if (dialog.open && dialog.dataset.expertId === expertId && dialog.dataset.interviewId === interviewId) {
          loadInterviewSummary();
        }
      }, 2500);
    }
  }

  async function loadInterviewSummary() {
    const dialog = document.getElementById("expert-interview-summary-dialog");
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    const expertId = dialog.dataset.expertId || "";
    const interviewId = dialog.dataset.interviewId || "";
    if (!expertId || !interviewId) {
      return;
    }
    try {
      const response = await fetch(summaryEndpoint(expertId, interviewId), { headers: { "Accept": "application/json" } });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "摘要状态读取失败");
      }
      if (dialog.dataset.expertId === expertId && dialog.dataset.interviewId === interviewId) {
        renderSummaryPayload(payload);
      }
    } catch (error) {
      clearSummaryPoll();
      setSummaryState("暂时无法读取摘要", error.message || "请稍后刷新。", "error");
    }
  }

  function openInterviewSummary(expert, interview) {
    const dialog = document.getElementById("expert-interview-summary-dialog");
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    clearSummaryPoll();
    dialog.dataset.expertId = String(expert.id || "");
    dialog.dataset.interviewId = String(interview.id || "");
    const title = dialog.querySelector("[data-summary-dialog-title]");
    const subtitle = dialog.querySelector("[data-summary-dialog-subtitle]");
    const content = dialog.querySelector("[data-summary-content]");
    const generateButton = dialog.querySelector("[data-summary-generate]");
    if (title) {
      title.textContent = (expert.name || "未命名专家") + " · 访谈摘要";
    }
    if (subtitle) {
      subtitle.textContent = [interview.display_time || interview.occurred_at, interview.title]
        .filter(Boolean).join(" · ") || "逐项结论只基于关联转录生成。";
    }
    if (content) {
      content.hidden = true;
    }
    if (generateButton) {
      generateButton.hidden = true;
    }
    setSummaryState("正在读取摘要", "请稍候。", "loading");
    openDialog(dialog);
    loadInterviewSummary();
  }

  const interviewSummaryDialog = document.getElementById("expert-interview-summary-dialog");
  const summaryRefreshButton = document.querySelector("[data-summary-refresh]");
  const summaryGenerateButton = document.querySelector("[data-summary-generate]");

  if (interviewSummaryDialog instanceof HTMLDialogElement) {
    interviewSummaryDialog.addEventListener("close", clearSummaryPoll);
  }

  if (summaryRefreshButton) {
    summaryRefreshButton.addEventListener("click", function () {
      setSummaryState("正在刷新摘要", "请稍候。", "loading");
      loadInterviewSummary();
    });
  }

  if (summaryGenerateButton) {
    summaryGenerateButton.addEventListener("click", async function () {
      if (!(interviewSummaryDialog instanceof HTMLDialogElement)) {
        return;
      }
      const expertId = interviewSummaryDialog.dataset.expertId || "";
      const interviewId = interviewSummaryDialog.dataset.interviewId || "";
      if (!expertId || !interviewId) {
        return;
      }
      try {
        clearSummaryPoll();
        summaryGenerateButton.disabled = true;
        summaryGenerateButton.textContent = "正在提交…";
        setSummaryState("正在加入后台队列", "页面可以关闭，生成完成后再回来查看。", "loading");
        const response = await fetch(summaryEndpoint(expertId, interviewId, "/generate"), {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ force: true })
        });
        const payload = await response.json();
        if (!payload || payload.ok !== true) {
          throw new Error(payload && payload.message || "摘要任务提交失败");
        }
        renderSummaryPayload(payload);
      } catch (error) {
        setSummaryState("摘要任务未提交", error.message || "请稍后重试。", "error");
        summaryGenerateButton.disabled = false;
        summaryGenerateButton.textContent = "重新尝试";
      }
    });
  }

  function collectInterviewData(container) {
    syncInterviewDateTime(container, "occurred_at");
    syncInterviewDateTime(container, "ended_at");
    const formData = new FormData();
    container.querySelectorAll("[data-interview-field]").forEach(function (field) {
      formData.set(field.dataset.interviewField, field.value || "");
    });
    return formData;
  }

  function interviewDraftKey(expertId, interviewId) {
    return interviewDraftPrefix + String(expertId || "") + ":" + String(interviewId || "new");
  }

  function interviewDraftPayload(container) {
    const fields = {};
    container.querySelectorAll("[data-interview-field]").forEach(function (field) {
      fields[field.dataset.interviewField || ""] = field.value || "";
    });
    return { version: 1, savedAt: Date.now(), fields: fields };
  }

  function saveInterviewDraft(container, expertId, interviewId, statusNode) {
    try {
      window.localStorage.setItem(
        interviewDraftKey(expertId, interviewId),
        JSON.stringify(interviewDraftPayload(container))
      );
      container.dataset.interviewDraftDirty = "1";
      if (statusNode) {
        statusNode.textContent = "草稿已保存在当前浏览器";
      }
    } catch (error) {
      if (statusNode) {
        statusNode.textContent = "浏览器未允许保存草稿";
      }
    }
  }

  function scheduleInterviewDraft(container, expertId, interviewId, statusNode) {
    const pending = interviewDraftTimers.get(container);
    if (pending) {
      window.clearTimeout(pending);
    }
    if (statusNode) {
      statusNode.textContent = "内容有变化，稍后保存草稿…";
    }
    container.dataset.interviewDraftDirty = "1";
    interviewDraftTimers.set(container, window.setTimeout(function () {
      saveInterviewDraft(container, expertId, interviewId, statusNode);
      interviewDraftTimers.delete(container);
    }, 1800));
  }

  function clearInterviewDraft(expertId, interviewId, container) {
    if (container) {
      const pending = interviewDraftTimers.get(container);
      if (pending) {
        window.clearTimeout(pending);
        interviewDraftTimers.delete(container);
      }
      container.dataset.interviewDraftDirty = "0";
    }
    try {
      window.localStorage.removeItem(interviewDraftKey(expertId, interviewId));
    } catch (error) {
      // Browser storage is optional; the server save has already succeeded.
    }
  }

  function restoreInterviewDraft(container, expertId, interviewId, statusNode) {
    let draft = null;
    try {
      const raw = window.localStorage.getItem(interviewDraftKey(expertId, interviewId));
      draft = raw ? JSON.parse(raw) : null;
      if (!draft || Date.now() - Number(draft.savedAt || 0) > interviewDraftTtl) {
        window.localStorage.removeItem(interviewDraftKey(expertId, interviewId));
        return false;
      }
    } catch (error) {
      return false;
    }
    Object.entries(draft.fields || {}).forEach(function (entry) {
      const field = container.querySelector('[data-interview-field="' + entry[0] + '"]');
      if (field) {
        field.value = entry[1] || "";
      }
    });
    initializeInterviewDateTime(container);
    container.dataset.interviewDraftDirty = "1";
    if (statusNode) {
      statusNode.textContent = "已恢复上次未保存草稿";
    }
    return true;
  }

  function enableInterviewDraft(container, expertId, interviewId, statusNode) {
    if (!container) {
      return;
    }
    container.dataset.interviewDraftExpertId = String(expertId || "");
    container.dataset.interviewDraftInterviewId = String(interviewId || "new");
    if (container.dataset.interviewDraftReady === "1") {
      return;
    }
    container.dataset.interviewDraftReady = "1";
    container.addEventListener("input", function (event) {
      if (event.target instanceof Element && event.target.matches("[data-interview-field], [data-interview-date-part], [data-interview-time-part]")) {
        scheduleInterviewDraft(container, container.dataset.interviewDraftExpertId, container.dataset.interviewDraftInterviewId, container.querySelector("[data-interview-draft-status]"));
      }
    });
    container.addEventListener("change", function (event) {
      if (event.target instanceof Element && event.target.matches("[data-interview-field], [data-interview-date-part], [data-interview-time-part]")) {
        scheduleInterviewDraft(container, container.dataset.interviewDraftExpertId, container.dataset.interviewDraftInterviewId, container.querySelector("[data-interview-draft-status]"));
      }
    });
  }

  function flushOpenInterviewDraft(dialog) {
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    const expertId = dialog.dataset.expertId || "";
    const composer = dialog.querySelector("[data-interview-composer]");
    if (expertId && composer && composer.dataset.interviewDraftDirty === "1") {
      const pending = interviewDraftTimers.get(composer);
      if (pending) {
        window.clearTimeout(pending);
        interviewDraftTimers.delete(composer);
      }
      saveInterviewDraft(composer, expertId, "new", composer.querySelector("[data-interview-draft-status]"));
    }
    dialog.querySelectorAll("[data-interview-edit-id]").forEach(function (container) {
      if (container.dataset.interviewDraftDirty === "1") {
        const pending = interviewDraftTimers.get(container);
        if (pending) {
          window.clearTimeout(pending);
          interviewDraftTimers.delete(container);
        }
        saveInterviewDraft(container, expertId, container.dataset.interviewEditId, container.querySelector("[data-interview-draft-status]"));
      }
    });
  }

  async function submitInterview(url, formData, message, onSuccess) {
    const response = await fetch(url, { method: "POST", body: formData });
    if (!response.ok) {
      throw new Error(message || "访谈记录保存失败");
    }
    if (typeof onSuccess === "function") {
      onSuccess();
    }
    const dialog = document.getElementById("expert-portfolio-interviews-dialog");
    const expertId = dialog ? dialog.dataset.expertId : "";
    if (expertId) {
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.delete("expert");
      nextUrl.searchParams.set("interviews", expertId);
      window.location.assign(nextUrl.pathname + nextUrl.search + nextUrl.hash);
      return;
    }
    window.location.reload();
  }

  function renderInterviewTimeline(expert) {
    const list = document.querySelector("[data-interview-list]");
    const count = document.querySelector("[data-interview-count]");
    if (!list) {
      return;
    }
    const interviews = Array.isArray(expert.interviews) ? expert.interviews : [];
    list.replaceChildren();
    if (count) {
      count.textContent = String(interviews.length);
    }
    if (!interviews.length) {
      const empty = document.createElement("p");
      empty.className = "section-caption";
      empty.textContent = "尚无访谈记录。首次约访后可在这里持续追加，并关联对应语音转录。";
      list.appendChild(empty);
      return;
    }
    interviews.forEach(function (interview) {
      const card = document.createElement("article");
      card.className = "expert-portfolio-interview-card";
      const head = document.createElement("div");
      head.className = "expert-portfolio-interview-card-head";
      const identity = document.createElement("div");
      const time = document.createElement("span");
      time.className = "section-caption";
      time.textContent = interview.display_time || interview.occurred_at || "时间待补充";
      const title = document.createElement("h5");
      title.textContent = (interview.interview_sequence ? "第 " + interview.interview_sequence + " 次 · " : "") + (interview.title || "专家访谈");
      identity.append(time, title);
      const status = document.createElement("span");
      status.className = "status-pill is-" + (interview.status_tone || "pending");
      status.textContent = interview.status_label || interview.status || "待安排";
      head.append(identity, status);
      card.appendChild(head);

      const interviewer = document.createElement("p");
      interviewer.className = "expert-portfolio-interview-person";
      interviewer.textContent = "访谈人：" + (interview.interviewer || "待填写");
      card.appendChild(interviewer);

      const resourceActions = document.createElement("div");
      resourceActions.className = "expert-portfolio-interview-resource-actions";
      if (interview.transcript_url) {
        const link = document.createElement("a");
        link.className = "button button-secondary button-compact";
        link.href = interview.transcript_url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = "打开关联语音转录";
        resourceActions.appendChild(link);
      }
      const summaryButton = document.createElement("button");
      summaryButton.type = "button";
      summaryButton.className = "button button-secondary button-compact expert-interview-summary-open";
      summaryButton.classList.toggle("is-ready", interview.ai_summary_status === "ready");
      summaryButton.textContent = "查看摘要";
      summaryButton.addEventListener("click", function () {
        openInterviewSummary(expert, interview);
      });
      resourceActions.appendChild(summaryButton);
      card.appendChild(resourceActions);
      appendTextBlock(card, "访谈备注", interview.notes);
      appendTextBlock(card, "调研反馈", interview.research_feedback);
      appendTextBlock(card, "未来跟踪", interview.future_tracking);
      appendTextBlock(card, "转录核对", interview.transcription_notes);

      if (!readonly) {
        const editor = document.createElement("details");
        editor.className = "expert-portfolio-interview-editor";
        const summary = document.createElement("summary");
        summary.textContent = "编辑这次访谈";
        const grid = document.createElement("div");
        grid.className = "expert-portfolio-interview-editor-grid";
        grid.dataset.interviewEditId = interview.id;
        grid.append(
          makeInterviewDateTimeField("访谈时间", "occurred_at", interview.occurred_at),
          makeInterviewDateTimeField("结束时间", "ended_at", interview.ended_at),
          makeInterviewDurationActions(),
          makeInterviewField("原始时间说明", "display_time", interview.display_time),
          makeInterviewField("访谈主题", "title", interview.title),
          makeInterviewField("访谈人", "interviewer", interview.interviewer),
          makeInterviewField("访谈状态", "status", interview.status, "select", interviewStatusOptions()),
          makeInterviewField("配额统计", "quota_status", interview.quota_status, "select", quotaStatusOptions()),
          makeInterviewField("关联语音转录", "transcript_id", interview.transcript_id, "select", transcriptOptions(interview.transcript_id)),
          makeInterviewField("来源", "source_label", interview.source_label),
          makeInterviewField("访谈备注", "notes", interview.notes, "textarea"),
          makeInterviewField("调研反馈", "research_feedback", interview.research_feedback, "textarea"),
          makeInterviewField("未来跟踪", "future_tracking", interview.future_tracking, "textarea"),
          makeInterviewField("转录核对状态", "transcription_quality", interview.transcription_quality, "select", transcriptionQualityOptions()),
          makeInterviewField("转录误差说明", "transcription_notes", interview.transcription_notes, "textarea")
        );
        const actions = document.createElement("div");
        actions.className = "expert-portfolio-interview-editor-actions";
        const draftStatus = document.createElement("span");
        draftStatus.className = "expert-interview-draft-status";
        draftStatus.dataset.interviewDraftStatus = "";
        draftStatus.textContent = "草稿仅保存在当前浏览器";
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "danger-button danger-button-compact";
        remove.textContent = "删除记录";
        remove.addEventListener("click", async function () {
          if (!window.confirm("确定删除这次访谈记录吗？关联的语音转录不会被删除。")) {
            return;
          }
          try {
            await submitInterview(
              "/expert-portfolio/experts/" + encodeURIComponent(expert.id) + "/interviews/" + encodeURIComponent(interview.id) + "/delete",
              new FormData(),
              "删除失败",
              function () { clearInterviewDraft(expert.id, interview.id, grid); }
            );
          } catch (error) {
            showToast(error.message || "删除失败", true);
          }
        });
        const save = document.createElement("button");
        save.type = "button";
        save.className = "button button-primary button-compact";
        save.textContent = "保存访谈";
        save.addEventListener("click", async function () {
          try {
            save.disabled = true;
            await submitInterview(
              "/expert-portfolio/experts/" + encodeURIComponent(expert.id) + "/interviews/" + encodeURIComponent(interview.id) + "/update",
              collectInterviewData(grid),
              "保存失败",
              function () { clearInterviewDraft(expert.id, interview.id, grid); }
            );
          } catch (error) {
            save.disabled = false;
            showToast(error.message || "保存失败", true);
          }
        });
        actions.append(remove, draftStatus, save);
        grid.appendChild(actions);
        editor.append(summary, grid);
        card.appendChild(editor);
        initializeInterviewDateTime(grid);
        grid.querySelectorAll("[data-interview-duration]").forEach(function (button) {
          button.addEventListener("click", function () {
            setInterviewDuration(grid, button.dataset.interviewDuration);
          });
        });
        restoreInterviewDraft(grid, expert.id, interview.id, draftStatus);
        enableInterviewDraft(grid, expert.id, interview.id, draftStatus);
      }
      list.appendChild(card);
    });
  }

  function resetInterviewComposer(dialog) {
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    const fold = dialog.querySelector(".expert-portfolio-interview-create-fold");
    if (fold instanceof HTMLDetailsElement) {
      fold.open = false;
    }
    dialog.querySelectorAll("[data-interview-composer] [data-interview-field]").forEach(function (field) {
      const key = field.dataset.interviewField || "";
      if (key === "title") {
        field.value = "Token economics 专家访谈";
      } else if (key === "status") {
        field.value = "planned";
      } else if (key === "transcription_quality") {
        field.value = "needs-review";
      } else {
        field.value = "";
      }
    });
    const composer = dialog.querySelector("[data-interview-composer]");
    if (composer) {
      composer.dataset.interviewDraftDirty = "0";
      initializeInterviewDateTime(composer);
    }
  }

  function openInterviews(expertId, options) {
    const expert = expertsById.get(String(expertId));
    const dialog = document.getElementById("expert-portfolio-interviews-dialog");
    if (!expert || !(dialog instanceof HTMLDialogElement)) {
      return;
    }
    dialog.dataset.expertId = String(expert.id);
    const title = dialog.querySelector("[data-interview-dialog-title]");
    const subtitle = dialog.querySelector("[data-interview-dialog-subtitle]");
    if (title) {
      title.textContent = (expert.name || "未命名专家") + " · 访谈记录";
    }
    if (subtitle) {
      subtitle.textContent = [expert.current_employer || expert.main_company, expert.current_title]
        .filter(Boolean)
        .join(" · ") || "专家机构与职位待补充";
    }
    const backButton = dialog.querySelector("[data-interview-dialog-back]");
    const returnTarget = options && options.returnToCalendar
      ? "calendar"
      : options && options.returnToQuota
        ? "quota"
        : "";
    dialog.dataset.returnTarget = returnTarget;
    if (backButton) {
      backButton.hidden = !returnTarget;
      backButton.textContent = returnTarget === "quota" ? "← 返回已访谈信息" : "← 返回日程";
    }
    resetInterviewComposer(dialog);
    renderInterviewTimeline(expert);
    const composer = dialog.querySelector("[data-interview-composer]");
    if (composer) {
      const draftStatus = composer.querySelector("[data-interview-draft-status]");
      if (!restoreInterviewDraft(composer, expert.id, "new", draftStatus) && draftStatus) {
        draftStatus.textContent = "草稿仅保存在当前浏览器";
      }
      enableInterviewDraft(composer, expert.id, "new", draftStatus);
      composer.querySelectorAll("[data-interview-duration]").forEach(function (button) {
        if (button.dataset.durationReady === "1") {
          return;
        }
        button.dataset.durationReady = "1";
        button.addEventListener("click", function () {
          setInterviewDuration(composer, button.dataset.interviewDuration);
        });
      });
    }
    openDialog(dialog);
  }

  function openExpert(expertId) {
    const expert = expertsById.get(String(expertId));
    const dialog = document.getElementById("expert-portfolio-detail-dialog");
    const form = dialog ? dialog.querySelector("[data-expert-detail-form]") : null;
    if (!expert || !(dialog instanceof HTMLDialogElement) || !(form instanceof HTMLFormElement)) {
      return;
    }
    form.action = "/expert-portfolio/experts/" + encodeURIComponent(expert.id) + "/update";
    dialog.dataset.expertId = String(expert.id);
    fillInput(form, "name", expert.name);
    fillInput(form, "vendors", (expert.vendors || []).join(", "));
    fillInput(form, "vendor_index", vendorIndexText(expert.vendor_index));
    fillInput(form, "current_title", expert.current_title);
    fillInput(form, "current_employer", expert.current_employer);
    fillInput(form, "main_company", expert.main_company);
    fillInput(form, "category", expert.category);
    fillInput(form, "industry", expert.industry);
    fillInput(form, "company_scale", expert.company_scale);
    fillInput(form, "region", expert.region);
    fillInput(form, "source_record_id", expert.source_record_id);
    fillInput(form, "status", expert.status);
    fillInput(form, "date_added", expert.date_added);
    fillInput(form, "description", expert.description);
    fillInput(form, "job_history", jobHistoryText(expert.job_history));
    fillInput(form, "notes", expert.notes);
    fillInput(form, "expert_comment", expert.expert_comment);
    fillInput(form, "data_quality_status", expert.data_quality_status);
    fillInput(form, "data_quality_notes", expert.data_quality_notes);
    fillInput(form, "source_label", expert.source_label);
    fillInput(form, "source_emails", (expert.source_emails || []).join(", "));
    fillInput(form, "duplicate_note", expert.duplicate_note);
    const title = dialog.querySelector("[data-expert-detail-title]");
    if (title) {
      title.textContent = expert.name || "专家详情";
    }
    const deleteForm = dialog.querySelector("[data-expert-delete-form]");
    if (deleteForm instanceof HTMLFormElement) {
      deleteForm.action = "/expert-portfolio/experts/" + encodeURIComponent(expert.id) + "/delete";
    }
    if (readonly) {
      form.querySelectorAll("input, textarea, select, button[type='submit']").forEach(function (field) {
        field.disabled = true;
      });
      const deleteButton = dialog.querySelector("[data-expert-delete]");
      if (deleteButton) {
        deleteButton.hidden = true;
      }
    }
    openDialog(dialog);
  }

  const interviewDialogBackButton = document.querySelector("[data-interview-dialog-back]");
  if (interviewDialogBackButton) {
    interviewDialogBackButton.addEventListener("click", function () {
      const interviewDialog = document.getElementById("expert-portfolio-interviews-dialog");
      const returnTarget = interviewDialog ? interviewDialog.dataset.returnTarget : "";
      closeDialog(interviewDialog);
      window.requestAnimationFrame(function () {
        openDialog(
          returnTarget === "quota"
            ? document.getElementById("expert-portfolio-quota-dialog")
            : calendarDialog
        );
      });
    });
  }

  const interviewCreateButton = document.querySelector("[data-interview-create]");
  if (interviewCreateButton) {
    interviewCreateButton.addEventListener("click", async function () {
      const dialog = document.getElementById("expert-portfolio-interviews-dialog");
      const composer = document.querySelector("[data-interview-composer]");
      const expertId = dialog ? dialog.dataset.expertId : "";
      if (!expertId || !composer) {
        return;
      }
      try {
        interviewCreateButton.disabled = true;
        interviewCreateButton.textContent = "正在保存…";
        await submitInterview(
          "/expert-portfolio/experts/" + encodeURIComponent(expertId) + "/interviews",
          collectInterviewData(composer),
          "新增访谈记录失败",
          function () { clearInterviewDraft(expertId, "new", composer); }
        );
      } catch (error) {
        interviewCreateButton.disabled = false;
        interviewCreateButton.textContent = "保存访谈记录";
        showToast(error.message || "新增访谈记录失败", true);
      }
    });
  }

  window.addEventListener("pagehide", function () {
    flushOpenInterviewDraft(document.getElementById("expert-portfolio-interviews-dialog"));
  });

  document.querySelectorAll("[data-interviews-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      openInterviews(button.dataset.interviewsOpen);
    });
  });

  document.querySelectorAll("[data-quota-expert-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      closeDialog(document.getElementById("expert-portfolio-quota-dialog"));
      window.requestAnimationFrame(function () {
        openInterviews(button.dataset.quotaExpertOpen, { returnToQuota: true });
      });
    });
  });

  document.querySelectorAll("[data-expert-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      openExpert(button.dataset.expertOpen);
    });
  });

  rows.forEach(function (row) {
    row.addEventListener("click", function (event) {
      const target = event.target;
      if (target instanceof Element && target.closest("input, select, button, a, textarea")) {
        return;
      }
      openExpert(row.dataset.expertId);
    });
    row.addEventListener("keydown", function (event) {
      if ((event.key === "Enter" || event.key === " ") && event.target === row) {
        event.preventDefault();
        openExpert(row.dataset.expertId);
      }
    });
  });

  const deleteButton = document.querySelector("[data-expert-delete]");
  if (deleteButton) {
    deleteButton.addEventListener("click", function () {
      const dialog = document.getElementById("expert-portfolio-detail-dialog");
      const title = dialog ? dialog.querySelector("[data-expert-detail-title]") : null;
      if (!window.confirm("确定删除专家“" + (title ? title.textContent : "") + "”吗？此操作不会影响原来的专家记录模块。")) {
        return;
      }
      const form = dialog ? dialog.querySelector("[data-expert-delete-form]") : null;
      if (form instanceof HTMLFormElement) {
        form.submit();
      }
    });
  }

  async function saveInlineField(row, field, value, control) {
    try {
      control.classList.add("is-saving");
      const response = await fetch(
        "/expert-portfolio/experts/" + encodeURIComponent(row.dataset.expertId || "") + "/field",
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ field: field, value: value })
        }
      );
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "保存失败");
      }
      const expert = payload.expert || {};
      expertsById.set(String(expert.id), expert);
      if (field === "category") {
        row.dataset.category = normalize(value);
        row.dataset.sortCategory = normalize(value);
      } else if (field === "status") {
        row.dataset.status = String(value);
        row.dataset.sortStatus = String(value);
        control.className = "expert-portfolio-status is-" + (statusTones[value] || "pending");
        control.dataset.inlineField = "status";
      } else if (field === "main_company") {
        row.dataset.sortCompany = normalize(value);
      }
      Object.entries(payload.stats || {}).forEach(function (entry) {
        const statNode = document.querySelector('[data-portfolio-stat="' + entry[0] + '"]');
        if (statNode) {
          statNode.textContent = String(entry[1]);
        }
      });
      showToast(payload.message || "已保存", false);
      applyFilters();
    } catch (error) {
      showToast(error.message || "保存失败", true);
    } finally {
      control.classList.remove("is-saving");
    }
  }

  if (!readonly) {
    document.querySelectorAll("[data-inline-field]").forEach(function (control) {
      const eventName = control instanceof HTMLInputElement ? "change" : "change";
      control.addEventListener(eventName, function () {
        const row = control.closest("[data-expert-id]");
        if (!row) {
          return;
        }
        saveInlineField(row, control.dataset.inlineField, control.value, control);
      });
    });
  }

  document.querySelectorAll("[data-confirm-category-delete]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      if (!window.confirm("删除分类后，相关专家会移到“未分类”。确定继续吗？")) {
        event.preventDefault();
      }
    });
  });

  function appendWarning(container, message) {
    const item = document.createElement("p");
    item.textContent = message;
    container.appendChild(item);
  }

  const intakeProviderSelect = document.querySelector("[data-intake-provider]");
  const intakeProviderStatus = document.querySelector("[data-intake-provider-status]");
  const intakeThinking = document.querySelector("[data-intake-thinking]");
  const intakeReasoning = document.querySelector("[data-intake-reasoning]");
  const intakeSource = document.querySelector("[data-intake-source]");
  const intakeCharCount = document.querySelector("[data-intake-char-count]");
  const intakeParseButton = document.querySelector("[data-intake-parse]");
  const intakePreview = document.querySelector("[data-intake-preview]");
  const intakePreviewTitle = document.querySelector("[data-intake-preview-title]");
  const intakeWarnings = document.querySelector("[data-intake-warnings]");
  const intakeCards = document.querySelector("[data-intake-cards]");
  const intakeImportButton = document.querySelector("[data-intake-import]");

  function selectedIntakeProvider() {
    const providerId = intakeProviderSelect ? intakeProviderSelect.value : "";
    return intakeProviders.find(function (provider) {
      return provider.id === providerId;
    });
  }

  function updateIntakeProviderState() {
    const provider = selectedIntakeProvider();
    const configured = Boolean(provider && provider.configured);
    if (intakeProviderStatus) {
      intakeProviderStatus.className = "status-pill " + (configured ? "is-success" : "is-warning");
      intakeProviderStatus.textContent = configured ? "接口已就绪" : "等待配置 API Key";
    }
    if (intakeParseButton) {
      intakeParseButton.disabled = readonly || !configured;
      intakeParseButton.title = configured ? "" : "请先在服务器环境变量中配置该接口的 API Key";
    }
    if (intakeThinking) {
      const supported = Boolean(provider && provider.supports_thinking);
      intakeThinking.disabled = readonly || !supported;
      if (!supported) {
        intakeThinking.checked = false;
      }
    }
    if (intakeReasoning) {
      const hasEfforts = Boolean(provider && Array.isArray(provider.reasoning_efforts) && provider.reasoning_efforts.length);
      intakeReasoning.disabled = readonly || !hasEfforts || !intakeThinking || !intakeThinking.checked;
    }
  }

  function populateIntakeReasoning(provider) {
    if (!intakeReasoning) {
      return;
    }
    const labels = { low: "低", medium: "中", high: "高", xhigh: "超高", max: "最大" };
    const efforts = provider && Array.isArray(provider.reasoning_efforts) ? provider.reasoning_efforts : [];
    intakeReasoning.replaceChildren();
    efforts.forEach(function (effort) {
      const option = document.createElement("option");
      option.value = effort;
      option.textContent = labels[effort] || effort;
      option.selected = effort === provider.default_reasoning_effort;
      intakeReasoning.appendChild(option);
    });
    if (!efforts.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "当前接口不支持";
      intakeReasoning.appendChild(option);
    }
  }

  async function loadIntakeProviders() {
    if (!intakeProviderSelect) {
      return;
    }
    try {
      const response = await fetch("/expert-intake/providers", { headers: { "Accept": "application/json" } });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "接口配置读取失败");
      }
      intakeProviders = Array.isArray(payload.providers) ? payload.providers : [];
      intakeProviderSelect.replaceChildren();
      intakeProviders.forEach(function (provider) {
        const option = document.createElement("option");
        option.value = provider.id;
        option.textContent = provider.label + (provider.model ? " · " + provider.model : "") + (provider.configured ? "" : "（未配置密钥）");
        intakeProviderSelect.appendChild(option);
      });
      if (!intakeProviders.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "没有可用接口";
        intakeProviderSelect.appendChild(option);
      }
      const initialProvider = selectedIntakeProvider();
      if (intakeThinking) {
        intakeThinking.checked = Boolean(initialProvider && initialProvider.default_thinking);
      }
      populateIntakeReasoning(initialProvider);
      updateIntakeProviderState();
    } catch (error) {
      intakeProviders = [];
      intakeProviderSelect.replaceChildren();
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "接口配置不可用";
      intakeProviderSelect.appendChild(option);
      if (intakeProviderStatus) {
        intakeProviderStatus.className = "status-pill is-danger";
        intakeProviderStatus.textContent = "模块不可用";
      }
      if (intakeParseButton) {
        intakeParseButton.disabled = true;
      }
      console.error("专家智能录入接口读取失败", error);
    }
  }

  function createIntakeField(label, field, value, options) {
    const settings = options || {};
    const wrapper = document.createElement("label");
    wrapper.className = "form-field" + (settings.wide ? " expert-intake-field-wide" : "");
    const caption = document.createElement("span");
    caption.className = "field-label";
    caption.textContent = label;
    const control = settings.multiline ? document.createElement("textarea") : document.createElement("input");
    control.dataset.intakeField = field;
    control.value = String(value || "");
    if (control instanceof HTMLTextAreaElement) {
      control.rows = settings.rows || 3;
    }
    wrapper.append(caption, control);
    return wrapper;
  }

  function intakeJobHistoryText(history) {
    return (Array.isArray(history) ? history : []).map(function (job) {
      return [job.title || "", job.company || "", job.dates || ""].join(" | ");
    }).join("\n");
  }

  function renderIntakePreview(payload) {
    parsedIntakeExperts = Array.isArray(payload.experts) ? payload.experts : [];
    if (!intakePreview || !intakePreviewTitle || !intakeWarnings || !intakeCards || !intakeImportButton) {
      return;
    }
    intakeWarnings.replaceChildren();
    intakeCards.replaceChildren();
    (payload.warnings || []).forEach(function (message) {
      appendWarning(intakeWarnings, message);
    });
    if (!(payload.warnings || []).length) {
      appendWarning(intakeWarnings, "模型提取可能存在遗漏或转录误差，请核对后再写入。当前结果尚未修改专家库。");
    }
    const provider = payload.provider || {};
    intakePreviewTitle.textContent = "识别到 " + parsedIntakeExperts.length + " 位专家" + (provider.model ? " · " + provider.model : "");
    parsedIntakeExperts.forEach(function (expert, index) {
      const card = document.createElement("article");
      card.className = "expert-intake-card";
      card.dataset.intakeIndex = String(index);

      const head = document.createElement("div");
      head.className = "expert-intake-card-head";
      const selection = document.createElement("label");
      selection.className = "expert-intake-card-selection";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.intakeSelected = "";
      const heading = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = expert.name || "未命名专家";
      const identity = document.createElement("small");
      identity.textContent = [expert.current_title, expert.current_employer].filter(Boolean).join(" · ") || "身份信息待核对";
      heading.append(name, identity);
      selection.append(checkbox, heading);
      const reviewBadge = document.createElement("span");
      reviewBadge.className = "status-pill is-warning";
      reviewBadge.textContent = "待人工核对";
      head.append(selection, reviewBadge);

      const fields = document.createElement("div");
      fields.className = "expert-intake-card-fields";
      fields.append(
        createIntakeField("姓名 *", "name", expert.name),
        createIntakeField("当前机构", "current_employer", expert.current_employer),
        createIntakeField("当前职位", "current_title", expert.current_title),
        createIntakeField("研究主公司", "main_company", expert.main_company),
        createIntakeField("行业", "industry", expert.industry),
        createIntakeField("公司规模", "company_scale", expert.company_scale),
        createIntakeField("地区", "region", expert.region),
        createIntakeField("分类", "category", expert.category),
        createIntakeField("专家渠道（逗号分隔）", "vendors", (expert.vendors || []).join(", ")),
        createIntakeField("来源编号", "source_record_id", expert.source_record_id),
        createIntakeField("履历（每行：职位 | 公司 | 时间）", "job_history", intakeJobHistoryText(expert.job_history), { wide: true, multiline: true, rows: 4 }),
        createIntakeField("资料摘要", "description", expert.description, { wide: true, multiline: true, rows: 4 }),
        createIntakeField("备注", "notes", expert.notes, { wide: true, multiline: true, rows: 3 }),
        createIntakeField("专家引述 / Comments（原文）", "expert_comment", expert.expert_comment, { wide: true, multiline: true, rows: 3 })
      );
      card.append(head, fields);
      intakeCards.appendChild(card);
    });
    intakePreview.hidden = false;
    intakeImportButton.disabled = readonly || !parsedIntakeExperts.length;
    intakePreview.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function intakeFieldValue(card, field) {
    const control = card.querySelector('[data-intake-field="' + field + '"]');
    return control ? control.value.trim() : "";
  }

  function collectIntakeExpert(card) {
    const index = Number(card.dataset.intakeIndex);
    const original = parsedIntakeExperts[index] || {};
    const result = Object.assign({}, original);
    ["name", "current_employer", "current_title", "main_company", "industry", "company_scale", "region", "category", "source_record_id", "description", "notes", "expert_comment"].forEach(function (field) {
      result[field] = intakeFieldValue(card, field);
    });
    result.data_quality_notes = "";
    result.vendors = intakeFieldValue(card, "vendors").split(/[,，;；\n]+/).map(function (item) {
      return item.trim();
    }).filter(Boolean);
    result.job_history = intakeFieldValue(card, "job_history").split(/\n+/).map(function (line) {
      const parts = line.split("|").map(function (item) { return item.trim(); });
      return { title: parts[0] || "", company: parts[1] || "", dates: parts.slice(2).join(" | ") };
    }).filter(function (job) {
      return job.title || job.company || job.dates;
    });
    result.status = "not-reviewed";
    result.data_quality_status = "needs-review";
    return result;
  }

  if (intakeProviderSelect) {
    intakeProviderSelect.addEventListener("change", function () {
      const provider = selectedIntakeProvider();
      if (intakeThinking) {
        intakeThinking.checked = Boolean(provider && provider.default_thinking);
      }
      populateIntakeReasoning(provider);
      updateIntakeProviderState();
    });
    loadIntakeProviders();
  }

  if (intakeThinking) {
    intakeThinking.addEventListener("change", updateIntakeProviderState);
  }

  if (intakeSource) {
    intakeSource.addEventListener("input", function () {
      if (intakeCharCount) {
        intakeCharCount.textContent = intakeSource.value.length.toLocaleString("zh-CN") + " / 40,000";
      }
    });
  }

  if (intakeParseButton) {
    intakeParseButton.addEventListener("click", async function () {
      const provider = selectedIntakeProvider();
      const sourceText = intakeSource ? intakeSource.value.trim() : "";
      if (!provider || !provider.configured) {
        showToast("请先配置模型接口的 API Key。", true);
        return;
      }
      if (sourceText.length < 10) {
        showToast("请粘贴更完整的专家信息。", true);
        return;
      }
      try {
        intakeParseButton.disabled = true;
        intakeParseButton.textContent = "正在识别…";
        const response = await fetch("/expert-intake/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({
            provider_id: provider.id,
            source_text: sourceText,
            thinking_enabled: Boolean(intakeThinking && intakeThinking.checked),
            reasoning_effort: intakeReasoning ? intakeReasoning.value : ""
          })
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "识别失败");
        }
        renderIntakePreview(payload);
      } catch (error) {
        showToast((error.message || "识别失败") + " 现有专家资料未受影响。", true);
      } finally {
        intakeParseButton.disabled = false;
        intakeParseButton.textContent = "识别并生成预览";
        updateIntakeProviderState();
      }
    });
  }

  if (intakeImportButton) {
    intakeImportButton.addEventListener("click", async function () {
      const selected = Array.from(document.querySelectorAll("[data-intake-index]")).filter(function (card) {
        const checkbox = card.querySelector("[data-intake-selected]");
        return checkbox && checkbox.checked;
      }).map(collectIntakeExpert).filter(function (expert) {
        return expert.name;
      });
      if (!selected.length) {
        showToast("请至少勾选并填写一位专家姓名。", true);
        return;
      }
      try {
        intakeImportButton.disabled = true;
        intakeImportButton.textContent = "正在写入…";
        const response = await fetch("/expert-portfolio/intake/import", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ experts: selected })
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "写入失败");
        }
        showToast(payload.message || "已写入专家库", false);
        window.setTimeout(function () {
          window.location.assign(payload.redirect_url || "/expert-portfolio");
        }, 500);
      } catch (error) {
        showToast((error.message || "写入失败") + " 请核对后重试。", true);
        intakeImportButton.disabled = false;
        intakeImportButton.textContent = "确认写入专家库";
      }
    });
  }

  const requestedExpertId = new URLSearchParams(window.location.search).get("expert");
  const requestedInterviewExpertId = new URLSearchParams(window.location.search).get("interviews");
  if (requestedInterviewExpertId && expertsById.has(requestedInterviewExpertId)) {
    openInterviews(requestedInterviewExpertId);
  } else if (requestedExpertId && expertsById.has(requestedExpertId)) {
    openExpert(requestedExpertId);
  }

  applyFilters();
})();
