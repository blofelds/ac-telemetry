"""Client-side shell state, global filter controller, and view dispatcher."""

from __future__ import annotations

REVIEW_SHELL_JS = r"""
(function () {
  const $ = (id) => document.getElementById(id);

  const state = {
    activeView: "overview",
    track: "All",
    car: "All",
    sessionType: "all",
    notesQuery: "",
    trimOutliers: true,
    hideEmpty: true,
    activityGroupBy: "track",
    inspectedSessionId: null,
    compareIds: [],
    payload: null,
    error: null,
  };

  window.REVIEW_VIEW_RENDERERS = window.REVIEW_VIEW_RENDERERS || {};

  function hasActiveFilters() {
    return (
      state.track !== "All" ||
      state.car !== "All" ||
      state.sessionType !== "all" ||
      state.notesQuery.trim() !== ""
    );
  }

  function updateFilterControls() {
    const H = window.REVIEW_HELPERS;
    const data = state.payload;
    if (!data) return;
    const opts = data.options || { tracks: [], cars: [] };
    const summary = data.summary || {};

    const trackSel = $("filter-track");
    trackSel.innerHTML =
      '<option value="All">All tracks (' + opts.tracks.length + ")</option>" +
      opts.tracks.map((t) => '<option value="' + H.escapeHtml(t) + '">' + H.escapeHtml(t) + "</option>").join("");
    trackSel.value = opts.tracks.includes(state.track) ? state.track : "All";

    const carSel = $("filter-car");
    carSel.innerHTML =
      '<option value="All">All cars (' + opts.cars.length + ")</option>" +
      opts.cars.map((c) => '<option value="' + H.escapeHtml(c) + '">' + H.escapeHtml(c) + "</option>").join("");
    carSel.value = opts.cars.includes(state.car) ? state.car : "All";

    document.querySelectorAll(".seg-btn[data-type]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-type") === state.sessionType);
    });

    $("btn-reset").classList.toggle("is-hidden", !hasActiveFilters());
    $("toggle-trim").checked = state.trimOutliers;
    $("toggle-empty").checked = state.hideEmpty;

    const outliers = summary.outlier_count || 0;
    $("trim-meta").textContent = state.trimOutliers ? "(" + outliers + " trimmed)" : "(raw laps)";
    const emptyN = summary.empty_session_count || 0;
    $("empty-meta").textContent = state.hideEmpty ? "(" + emptyN + " hidden)" : "(" + emptyN + " shown)";

    const lapText =
      state.trimOutliers && summary.raw_laps !== summary.visible_laps
        ? summary.visible_laps + "/" + summary.raw_laps
        : String(summary.visible_laps || 0);
    $("status-meta").textContent =
      (summary.session_count || 0) + " sessions · " +
      lapText + " laps · " +
      (summary.gt_confirmed_count || 0) + " GT-confirmed · * legacy blank as p";

    const notice = $("filter-notice");
    if (state.error) {
      notice.className = "notice notice-err";
      notice.textContent = "Could not load review data: " + state.error;
    } else if ((summary.total_sessions || 0) > 0 && (summary.session_count || 0) === 0) {
      notice.className = "notice";
      notice.innerHTML =
        '<span>No sessions matched the current filters. Reset filters or clear the notes search.</span>' +
        '<button type="button" class="btn-reset" id="notice-reset">Reset filters</button>';
      const nr = $("notice-reset");
      if (nr) nr.addEventListener("click", resetFilters);
    } else {
      notice.className = "notice is-hidden";
      notice.textContent = "";
    }
  }

  function getActiveCombo() {
    const combos = (state.payload && state.payload.combos) || [];
    if (!combos.length) return null;
    if (state.track !== "All" && state.car !== "All") {
      const hit = combos.find((c) => c.track === state.track && c.car === state.car);
      if (hit) return hit;
    }
    return combos[0];
  }

  function getActiveComboSessions() {
    const combo = getActiveCombo();
    const sessions = (state.payload && state.payload.sessions) || [];
    if (!combo) return [];
    return sessions.filter(
      (s) => s.track === combo.track && s.car === combo.car && (s.lap_count || 0) > 0
    );
  }

  function syncSelectionForPayload() {
    const comboSessions = getActiveComboSessions();
    if (!comboSessions.length) {
      state.inspectedSessionId = null;
      state.compareIds = [];
      return;
    }
    if (!comboSessions.some((s) => s.session_id === state.inspectedSessionId)) {
      state.inspectedSessionId = comboSessions[comboSessions.length - 1].session_id;
    }
    const valid = state.compareIds.filter((id) =>
      comboSessions.some((s) => s.session_id === id)
    );
    state.compareIds = valid.length >= 2
      ? valid.slice(0, 4)
      : comboSessions.slice(-Math.min(3, comboSessions.length)).map((s) => s.session_id);
  }

  function setActiveView(viewId) {
    state.activeView = viewId;
    document.querySelectorAll(".view-tab[data-view]").forEach((tab) => {
      const active = tab.getAttribute("data-view") === viewId;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    renderActiveView();
  }

  async function drillIntoCombo(track, car, sessionId) {
    state.track = track;
    state.car = car;
    if (sessionId) state.inspectedSessionId = sessionId;
    state.activeView = "progression";
    document.querySelectorAll(".view-tab[data-view]").forEach((tab) => {
      const active = tab.getAttribute("data-view") === "progression";
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    await fetchReviewData();
  }

  async function resetFilters() {
    state.track = "All";
    state.car = "All";
    state.sessionType = "all";
    state.notesQuery = "";
    $("filter-notes").value = "";
    await fetchReviewData();
  }

  function renderActiveView() {
    const H = window.REVIEW_HELPERS;
    const root = $("review-root");
    if (!root) return;
    if (!state.payload) {
      root.innerHTML = '<div class="card empty-state">Loading session visualisations…</div>';
      return;
    }
    const renderer = window.REVIEW_VIEW_RENDERERS[state.activeView];
    if (typeof renderer === "function") {
      renderer(root, state, H);
      return;
    }
    const combo = getActiveCombo();
    const label = combo ? combo.track + " · " + combo.car : "No combo selected";
    root.innerHTML =
      '<div class="card empty-state"><strong>' + H.escapeHtml(state.activeView) + "</strong>" +
      "View module not yet loaded (" + H.escapeHtml(label) + ").</div>";
  }

  let fetchSeq = 0;
  async function fetchReviewData() {
    const seq = ++fetchSeq;
    const params = new URLSearchParams();
    if (state.track !== "All") params.set("track", state.track);
    if (state.car !== "All") params.set("car", state.car);
    if (state.sessionType !== "all") params.set("session_type", state.sessionType);
    if (state.notesQuery.trim()) params.set("q", state.notesQuery.trim());
    params.set("trim_outliers", state.trimOutliers ? "true" : "false");
    params.set("hide_empty", state.hideEmpty ? "true" : "false");
    try {
      const resp = await fetch("/api/review?" + params.toString());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const payload = await resp.json();
      if (seq !== fetchSeq) return;
      state.payload = payload;
      state.error = null;
      syncSelectionForPayload();
      updateFilterControls();
      renderActiveView();
    } catch (err) {
      if (seq !== fetchSeq) return;
      state.error = String(err);
      updateFilterControls();
    }
  }

  window.REVIEW_HELPERS = Object.assign(window.REVIEW_HELPERS || {}, {
    getActiveCombo, getActiveComboSessions, drillIntoCombo, setActiveView,
    rerender: renderActiveView,
    selectInspectedSession(sid) { state.inspectedSessionId = sid; renderActiveView(); },
    toggleCompareSession(sid) {
      const list = state.compareIds.slice();
      const idx = list.indexOf(sid);
      if (idx !== -1) { if (list.length <= 2) return; list.splice(idx, 1); }
      else { if (list.length >= 4) list.shift(); list.push(sid); }
      state.compareIds = list;
      renderActiveView();
    },
    setActivityGroupBy(mode) { state.activityGroupBy = mode === "car" ? "car" : "track"; renderActiveView(); },
  });

  window.REVIEW_BOOT = function () {
    const H = window.REVIEW_HELPERS;
    $("theme-toggle").addEventListener("click", () => H.toggleTheme(renderActiveView));
    $("filter-track").addEventListener("change", (ev) => { state.track = ev.target.value; fetchReviewData(); });
    $("filter-car").addEventListener("change", (ev) => { state.car = ev.target.value; fetchReviewData(); });
    document.querySelectorAll(".seg-btn[data-type]").forEach((btn) => {
      btn.addEventListener("click", () => { state.sessionType = btn.getAttribute("data-type"); fetchReviewData(); });
    });
    let searchTimer = null;
    $("filter-notes").addEventListener("input", (ev) => {
      state.notesQuery = ev.target.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(fetchReviewData, 140);
    });
    $("btn-reset").addEventListener("click", resetFilters);
    $("toggle-trim").addEventListener("change", (ev) => { state.trimOutliers = !!ev.target.checked; fetchReviewData(); });
    $("toggle-empty").addEventListener("change", (ev) => { state.hideEmpty = !!ev.target.checked; fetchReviewData(); });
    document.querySelectorAll(".view-tab[data-view]").forEach((tab) => {
      tab.addEventListener("click", () => setActiveView(tab.getAttribute("data-view")));
    });
    H.syncThemeButton();
    fetchReviewData();
  };
})();
""".strip()
