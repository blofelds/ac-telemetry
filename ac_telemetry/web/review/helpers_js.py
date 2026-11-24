"""Shared client-side formatting, theme palette, and badge helpers for /review."""

from __future__ import annotations

REVIEW_HELPERS_JS = r"""
(function () {
  const THEME_KEY = "ac_telemetry_review_theme";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatLapMs(ms) {
    if (ms == null || !Number.isFinite(Number(ms))) return "--:--.---";
    const total = Math.round(Number(ms));
    if (total < 0) return "--:--.---";
    const mins = Math.floor(total / 60000);
    const secs = Math.floor((total % 60000) / 1000);
    const rem = total % 1000;
    return mins + ":" + String(secs).padStart(2, "0") + "." + String(rem).padStart(3, "0");
  }

  function formatDeltaMs(deltaMs) {
    if (deltaMs == null || !Number.isFinite(Number(deltaMs))) return "--";
    const val = Number(deltaMs);
    const sign = val >= 0 ? "+" : "-";
    return sign + (Math.abs(val) / 1000).toFixed(3) + "s";
  }

  function formatSecShort(sec) {
    const mins = Math.floor(sec / 60);
    const rem = sec - mins * 60;
    return mins + ":" + (rem < 10 ? "0" : "") + rem.toFixed(1);
  }

  function getThemePalette() {
    const cs = getComputedStyle(document.documentElement);
    const v = (name, fallback) => (cs.getPropertyValue(name) || "").trim() || fallback;
    return {
      bg: v("--bg", "#0b0e14"),
      surface: v("--surface", "#141923"),
      surfaceMuted: v("--surface-muted", "#0f141e"),
      border: v("--border", "#232c3d"),
      text: v("--text", "#e5e9f0"),
      textMuted: v("--text-muted", "#8892a6"),
      accent: v("--accent", "#3b82f6"),
      accentSoft: v("--accent-soft", "#16253f"),
      green: v("--green", "#10b981"),
      greenSoft: v("--green-soft", "#0e2922"),
      amber: v("--amber", "#f59e0b"),
      amberSoft: v("--amber-soft", "#2b2110"),
      red: v("--red", "#ef4444"),
      purple: v("--purple", "#a78bfa"),
      grid: v("--grid", "#1f2736"),
    };
  }

  function renderTypePill(effectiveType, isLegacy) {
    const isRace = effectiveType === "r";
    const cls = isRace ? "race" : "practice";
    const title = isLegacy
      ? "Legacy blank session_type: grouped under Practice (p)"
      : isRace
        ? "Race session (r)"
        : "Practice session (p)";
    const label = (isRace ? "Race (r)" : "Practice (p)") + (isLegacy ? "*" : "");
    return '<span class="pill-type ' + cls + '" title="' + escapeHtml(title) + '">' +
      escapeHtml(label) + "</span>";
  }

  function renderGtBadge() {
    return '<span class="badge-gt" title="Accuracy ground-truth confirmed stint">GT</span>';
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function syncThemeButton() {
    const light = currentTheme() === "light";
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.textContent = light ? "Dark Theme" : "Clean Light";
    btn.setAttribute("aria-pressed", light ? "true" : "false");
  }

  function toggleTheme(onChanged) {
    const next = currentTheme() === "light" ? "dark" : "light";
    if (next === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* ignore */ }
    syncThemeButton();
    if (typeof onChanged === "function") onChanged();
  }

  window.REVIEW_HELPERS = Object.assign(window.REVIEW_HELPERS || {}, {
    escapeHtml,
    formatLapMs,
    formatDeltaMs,
    formatSecShort,
    getThemePalette,
    renderTypePill,
    renderGtBadge,
    syncThemeButton,
    toggleTheme,
  });
})();
""".strip()
