"""Local browser web agent that tests the KSA SIM MCP tools."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ksa_sim.env import load_env
from ksa_sim.mcp_client import call_mcp_tool
from ksa_sim.off_topic import is_filter_follow_up, is_off_topic

HOST = "127.0.0.1"
PORT = int(os.environ.get("LOCAL_UI_PORT", "8768"))
load_env()

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>KSA SIM MCP — web agent</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --ink: #1a2421;
      --muted: #5c6b64;
      --line: #d4ddd7;
      --paper: #eef2ef;
      --card: #ffffff;
      --accent: #0f5c4c;
      --accent-ink: #ffffff;
      --user: #d8ebe4;
      --bot: #ffffff;
      --error: #8a1f1f;
      --error-bg: #fff0f0;
      --soft: #f2f7f4;
      --warn: #7a4a00;
      --warn-bg: #fff4df;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Source Sans 3", "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(ellipse 70% 45% at 100% 0%, rgba(15, 92, 76, 0.12), transparent 55%),
        linear-gradient(165deg, #e3ece7 0%, var(--paper) 50%, #dde7e1 100%);
      min-height: 100vh;
    }
    main {
      width: min(860px, calc(100% - 2rem));
      margin: 1.25rem auto 2rem;
      display: flex;
      flex-direction: column;
      min-height: calc(100vh - 3rem);
    }
    h1 {
      margin: 0 0 0.35rem;
      font-family: Fraunces, Georgia, serif;
      font-size: clamp(1.7rem, 3.8vw, 2.15rem);
      font-weight: 700;
      letter-spacing: -0.03em;
    }
    .sub {
      margin: 0 0 0.9rem;
      color: var(--muted);
      font-size: 0.98rem;
      line-height: 1.45;
    }
    .banner {
      margin: 0 0 0.85rem;
      padding: 0.75rem 1rem;
      border-radius: 12px;
      font-size: 0.95rem;
      background: var(--warn-bg);
      color: var(--warn);
    }
    .chat {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 16px 48px rgba(26, 36, 33, 0.07);
      overflow: hidden;
      min-height: 520px;
    }
    .thread {
      flex: 1;
      overflow-y: auto;
      padding: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.7rem;
      background: linear-gradient(180deg, #fafcfb, #f1f5f3);
    }
    .msg {
      max-width: min(100%, 820px);
      padding: 0.8rem 0.95rem;
      border-radius: 14px;
      border: 1px solid var(--line);
      line-height: 1.45;
      white-space: pre-wrap;
    }
    .msg.user {
      align-self: flex-end;
      background: var(--user);
      border-bottom-right-radius: 5px;
    }
    .msg.bot {
      align-self: flex-start;
      background: var(--bot);
      border-bottom-left-radius: 5px;
    }
    .msg.error { background: var(--error-bg); color: var(--error); }
    .msg .rich { white-space: normal; margin-top: 0.55rem; }
    .msg .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin: 0 0 0.65rem;
    }
    .chip {
      border: 1px solid #c9dbd3;
      background: var(--soft);
      border-radius: 8px;
      padding: 0.18rem 0.5rem;
      font-size: 0.78rem;
      font-weight: 600;
      color: #3f5349;
    }
    button.chip.option {
      cursor: pointer;
      font: inherit;
      font-size: 0.82rem;
      font-weight: 700;
      background: #fff;
      border-color: var(--accent);
      color: var(--accent);
    }
    button.chip.option:hover { background: var(--user); }
    .notice {
      margin-top: 0.65rem;
      padding: 0.65rem 0.75rem;
      border-radius: 10px;
      background: var(--warn-bg);
      color: var(--warn);
      font-size: 0.84rem;
      line-height: 1.4;
    }
    .results { display: grid; gap: 0.55rem; border-top: 1px solid var(--line); padding-top: 0.7rem; }
    .package {
      padding: 0.7rem 0.8rem;
      border-radius: 12px;
      background: var(--soft);
      border: 1px solid #e0ebe5;
    }
    .package-title { font-weight: 700; font-size: 0.98rem; letter-spacing: -0.015em; }
    .package-provider { color: var(--accent); font-weight: 700; font-size: 0.88rem; margin-bottom: 0.2rem; }
    .package-facts { color: var(--muted); font-size: 0.86rem; margin-top: 0.25rem; }
    .package a { color: var(--accent); font-weight: 600; font-size: 0.84rem; text-decoration: none; }
    .package a:hover { text-decoration: underline; }
    .package.best { border-color: #9ec9bb; background: #e7f4ee; }
    .recommend {
      margin-bottom: 0.8rem;
      padding: 0.85rem 0.9rem;
      border-radius: 12px;
      border: 1px solid #9ec9bb;
      background: #e7f4ee;
    }
    .recommend-kicker {
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 0.3rem;
    }
    .recommend p { margin: 0.35rem 0 0.55rem; }
    .recommend ul { margin: 0; padding-left: 1.1rem; color: #3f5349; font-size: 0.86rem; }
    .recommend li { margin: 0.2rem 0; }
    .badge {
      display: inline-block;
      margin-left: 0.35rem;
      padding: 0.05rem 0.4rem;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      font-size: 0.7rem;
      font-weight: 700;
      vertical-align: middle;
    }
    .composer {
      border-top: 1px solid var(--line);
      padding: 0.9rem;
      background: #fff;
      display: grid;
      gap: 0.65rem;
    }
    .composer details { color: var(--muted); font-size: 0.9rem; }
    .composer input[type="password"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0.55rem 0.75rem;
      font: inherit;
      margin-top: 0.35rem;
    }
    .row { display: flex; gap: 0.65rem; align-items: flex-end; }
    #chatInput {
      flex: 1;
      min-height: 3.2rem;
      max-height: 9rem;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 0.8rem 0.95rem;
      font: inherit;
      resize: vertical;
      background: #fbfcfb;
    }
    #sendBtn {
      border: 0;
      border-radius: 12px;
      background: var(--accent);
      color: var(--accent-ink);
      padding: 0.85rem 1.2rem;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      white-space: nowrap;
    }
    #sendBtn:disabled { opacity: 0.6; cursor: wait; }
    .hint { color: var(--muted); font-size: 0.85rem; }
    .compare-wrap {
      margin-top: 0.85rem;
      border-top: 1px solid var(--line);
      padding-top: 0.75rem;
      overflow-x: auto;
    }
    table.compare {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
      min-width: 640px;
    }
    table.compare th,
    table.compare td {
      text-align: left;
      padding: 0.4rem 0.45rem;
      border-bottom: 1px solid #e0ebe5;
      white-space: nowrap;
    }
    table.compare th {
      color: var(--accent);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }
    table.compare td.num { text-align: right; font-variant-numeric: tabular-nums; }
    table.compare tr.best { background: #e7f4ee; font-weight: 600; }
    table.compare caption {
      caption-side: top;
      text-align: left;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 0.4rem;
    }
    .compare-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem 0.75rem;
      align-items: center;
      margin: 0 0 0.5rem;
    }
    .compare-toolbar label {
      display: flex;
      align-items: center;
      gap: 0.3rem;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 600;
    }
    .compare-toolbar select {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 0.78rem;
      padding: 0.22rem 0.4rem;
    }
    .compare-hint { color: var(--muted); font-size: 0.75rem; font-weight: 500; }
    table.compare th.sortable { padding: 0; }
    table.compare .sort-btn {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      width: 100%;
      margin: 0;
      border: 0;
      background: transparent;
      color: var(--accent);
      font: inherit;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      text-align: left;
      padding: 0.4rem 0.45rem;
      cursor: pointer;
      white-space: nowrap;
    }
    table.compare .sort-btn:hover { background: #e7f4ee; }
    table.compare .sort-btn[aria-sort] { background: #e7f4ee; }
    table.compare .sort-ind { color: #7a958a; font-size: 0.72rem; font-weight: 700; }
    table.compare .sort-btn[aria-sort] .sort-ind { color: var(--accent); }
    table.compare tr[hidden] { display: none; }
  </style>
</head>
<body>
  <main>
    <h1>KSA SIM advisor</h1>
    <p class="sub">Web agent for the MCP server — ranks current tourist SIM packages in Saudi Arabia from official operator websites (STC, Mobily, Zain, Lebara, Virgin Mobile).</p>
    <section class="chat">
      <div id="thread" class="thread" aria-live="polite"></div>
      <form id="chatForm" class="composer">
        <div class="row">
          <textarea id="chatInput" rows="2" placeholder="e.g. data + voice SIM for 7 days under 100 SAR" required></textarea>
          <button id="sendBtn" type="submit">Send</button>
        </div>
        <div class="hint">Official KSA operator websites · Enter to send</div>
      </form>
    </section>
  </main>
  <script>
    const thread = document.getElementById("thread");
    const form = document.getElementById("chatForm");
    const input = document.getElementById("chatInput");
    const sendBtn = document.getElementById("sendBtn");

    let pendingRequest = "";
    let awaitingField = null;
    let lastFilters = null;
    const seenBotTexts = new Set();

    function readyForNewQuestion(placeholder) {
      pendingRequest = "";
      awaitingField = null;
      sendBtn.disabled = false;
      input.disabled = false;
      input.placeholder = placeholder || "Ask another question…";
      input.focus();
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function addMessage(role, text, extraHtml = "", options = {}) {
      if (role === "bot" && text && !options.skipDedupe && seenBotTexts.has(text) && !extraHtml) {
        text = text + "\n\n(Continuing from what we already covered — tell me what to change.)";
      }
      if (role === "bot" && text && !options.skipDedupe) {
        seenBotTexts.add(text);
      }
      const node = document.createElement("div");
      node.className = "msg " + role;
      node.textContent = text;
      if (extraHtml) {
        const wrap = document.createElement("div");
        wrap.className = "rich";
        wrap.innerHTML = extraHtml;
        node.appendChild(wrap);
      }
      thread.appendChild(node);
      thread.scrollTop = thread.scrollHeight;
      return node;
    }

    function chipsHtml(interpreted, mcpTool) {
      const labels = {
        service_type: "Need",
        trip_days: "Days",
        budget_sar: "Budget SAR",
        allow_any_budget: "Budget",
        providers: "Providers",
        sim_form: "SIM form",
        sort_by: "Sort",
      };
      const chips = Object.entries(interpreted || {}).map(([key, value]) => {
        const label = labels[key] || key;
        let shown = value;
        if (key === "allow_any_budget") shown = "Any";
        if (Array.isArray(value)) shown = value.join(", ");
        return `<span class="chip">${escapeHtml(label)}: ${escapeHtml(shown)}</span>`;
      });
      if (mcpTool) {
        chips.unshift(`<span class="chip">MCP: ${escapeHtml(mcpTool)}</span>`);
      }
      return chips.length ? `<div class="meta">${chips.join("")}</div>` : "";
    }

    function optionsHtml(options) {
      if (!options || !options.length) return "";
      return `<div class="meta">${options.map((item) => (
        `<button type="button" class="chip option" data-value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button>`
      )).join("")}</div>`;
    }

    function recommendationHtml(rec) {
      if (!rec) return "";
      const criteria = (rec.criteria || []).map((item) => (
        `<li><strong>${escapeHtml(item.name)}:</strong> ${escapeHtml(item.definition)} ${escapeHtml(item.assessment || "")}</li>`
      )).join("");
      return [
        '<div class="recommend">',
        '<div class="recommend-kicker">Best match</div>',
        `<div class="package-title">${escapeHtml(rec.title || rec.provider || "Recommended package")}</div>`,
        rec.summary ? `<p>${escapeHtml(rec.summary)}</p>` : "",
        criteria ? `<ul>${criteria}</ul>` : "",
        "</div>",
      ].join("");
    }

    function formatGb(value) {
      if (value == null) return "—";
      return value >= 999 ? "Unlimited" : value + " GB";
    }
    function formatMin(value) {
      if (value == null) return "—";
      return value >= 9999 ? "Unlimited" : value + " min";
    }
    function uniqueOptions(values) {
      return [...new Set(values.filter((value) => value != null && value !== ""))].sort();
    }
    function valueSortKey(value) {
      const match = String(value || "").match(/(\d+(?:\.\d+)?)/);
      return match ? match[1] : "";
    }
    function sortHeader(key, type, label) {
      return `<th class="sortable"><button type="button" class="sort-btn" data-key="${escapeHtml(key)}" data-type="${escapeHtml(type)}">${escapeHtml(label)} <span class="sort-ind" aria-hidden="true">↕</span></button></th>`;
    }
    function comparisonHtml(comparison) {
      if (!comparison || !comparison.length) return "";
      const providers = uniqueOptions(comparison.map((row) => row.provider));
      const intl = uniqueOptions(comparison.map((row) => row.international));
      const providerOptions = ['<option value="">All providers</option>'].concat(
        providers.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
      ).join("");
      const intlOptions = ['<option value="">All</option>'].concat(
        intl.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
      ).join("");
      const rows = comparison.map((row) => {
        const cls = row.recommended ? " best" : "";
        return `<tr class="${cls}" data-provider="${escapeHtml(row.provider || "")}" data-international="${escapeHtml(row.international || "")}">
          <td class="num" data-col="rank" data-sort="${row.rank ?? ""}">${row.rank ?? ""}</td>
          <td data-col="provider" data-sort="${escapeHtml((row.provider || "").toLowerCase())}">${escapeHtml(row.provider || "")}</td>
          <td data-col="plan" data-sort="${escapeHtml((row.plan || "").toLowerCase())}">${escapeHtml(row.plan || "")}${row.recommended ? ' <span class="badge">Best</span>' : ""}</td>
          <td class="num" data-col="price_sar" data-sort="${row.price_sar ?? ""}">${row.price_sar != null ? row.price_sar + " SAR" : "—"}</td>
          <td class="num" data-col="data_gb" data-sort="${row.data_gb ?? ""}">${escapeHtml(formatGb(row.data_gb))}</td>
          <td class="num" data-col="voice_minutes" data-sort="${row.voice_minutes ?? ""}">${escapeHtml(formatMin(row.voice_minutes))}</td>
          <td class="num" data-col="validity_days" data-sort="${row.validity_days ?? ""}">${row.validity_days != null ? row.validity_days : "—"}</td>
          <td data-col="value" data-sort="${escapeHtml(valueSortKey(row.value))}">${escapeHtml(row.value || "—")}</td>
          <td data-col="international" data-sort="${escapeHtml((row.international || "").toLowerCase())}">${escapeHtml(row.international || "—")}</td>
        </tr>`;
      }).join("");
      return `<div class="compare-wrap">
        <div class="recommend-kicker">Comparison</div>
        <div class="compare-toolbar">
          <label>Provider <select class="compare-filter" data-filter="provider" aria-label="Filter by provider">${providerOptions}</select></label>
          <label>International <select class="compare-filter" data-filter="international" aria-label="Filter by international calling">${intlOptions}</select></label>
          <span class="compare-hint">Click a column header to sort</span>
        </div>
        <table class="compare">
        <thead><tr>
          ${sortHeader("rank", "number", "#")}
          ${sortHeader("provider", "text", "Provider")}
          ${sortHeader("plan", "text", "Plan")}
          ${sortHeader("price_sar", "number", "Price")}
          ${sortHeader("data_gb", "number", "Data")}
          ${sortHeader("voice_minutes", "number", "Minutes")}
          ${sortHeader("validity_days", "number", "Days")}
          ${sortHeader("value", "number", "Value")}
          ${sortHeader("international", "text", "International")}
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
    }
    function packagesHtml(packages) {
      if (!packages || !packages.length) {
        return "<div class='package-facts'>No current packages extracted from sources.</div>";
      }
      return `<div class="results">${packages.map((item) => {
        const facts = [
          item.price_sar != null ? item.price_sar + " SAR" : (item.price_label || "Price not listed in source"),
          item.data_gb != null
            ? (item.data_gb >= 999 ? "Unlimited data" : item.data_gb + " GB")
            : (item.data_label || "Data not listed in source"),
          item.voice_minutes != null ? item.voice_minutes + " min" : null,
          item.validity_days != null ? item.validity_days + " days" : null,
        ].filter(Boolean).join(" · ");
        const checked = item.source_checked_at
          ? `<div class="package-facts">Source checked: ${escapeHtml(item.source_checked_at)}</div>`
          : "";
        const link = item.source_url
          ? `<div style="margin-top:0.35rem"><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">Source</a></div>`
          : "";
        const bestClass = item.recommended ? " best" : "";
        const badge = item.recommended ? '<span class="badge">Recommended</span>' : "";
        return [
          `<article class="package${bestClass}">`,
          `<div class="package-provider">#${item.rank || ""} ${escapeHtml(item.provider || "")}${badge}</div>`,
          `<div class="package-title">${escapeHtml(item.title || "Package")}</div>`,
          facts ? `<div class="package-facts">${escapeHtml(facts)}</div>` : "",
          item.summary ? `<div class="package-facts">${escapeHtml(item.summary)}</div>` : "",
          item.rank_reason ? `<div class="package-facts">${escapeHtml(item.rank_reason)}</div>` : "",
          checked,
          link,
          "</article>",
        ].join("");
      }).join("")}</div>`;
    }

    function replaceTripDays(base, days) {
      const cleaned = String(base || "").replace(/\s+for\s+\d+\s+days?\b/gi, "").trim();
      return `${cleaned} for ${days} days`.trim();
    }

    function mergeFollowUp(answer) {
      const trimmed = answer.trim();
      if (!pendingRequest) return trimmed;
      const overrideDays = trimmed.match(/(?:change(?:\s+it)?|update|switch|make\s+it|set(?:\s+it)?|instead).{0,20}?(\d+)\s*(?:day|days)?/i)
        || trimmed.match(/(\d+)\s*(?:day|days)\b/i);
      if (overrideDays && awaitingField !== "trip_days") {
        pendingRequest = replaceTripDays(pendingRequest, overrideDays[1]);
      }
      if (awaitingField === "service_type") {
        if (/^data$/i.test(trimmed)) return `${pendingRequest} data only`.trim();
        if (/^voice$/i.test(trimmed)) return `${pendingRequest} voice only`.trim();
        if (/^both$/i.test(trimmed)) return `${pendingRequest} data and voice`.trim();
      }
      if (awaitingField === "trip_days") {
        if (/^\d+$/.test(trimmed)) return replaceTripDays(pendingRequest, trimmed);
        if (overrideDays) return replaceTripDays(pendingRequest, overrideDays[1]);
      }
      if (awaitingField === "budget") {
        if (/^any$/i.test(trimmed)) return `${pendingRequest} any budget`.trim();
        if (/^\d+$/.test(trimmed) && !/day/i.test(trimmed)) {
          return `${pendingRequest} under ${trimmed} SAR`.trim();
        }
      }
      return `${pendingRequest} ${trimmed}`.trim();
    }

    async function runCompare(requestText) {
      sendBtn.disabled = true;
      input.disabled = true;
      const thinking = addMessage("bot", "Checking official operator websites…", "", { skipDedupe: true });
      try {
        const response = await fetch("/api/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            request: requestText,
            previous_filters: lastFilters,
          }),
        });
        const data = await response.json();
        thinking.remove();

        if (data.off_topic) {
          addMessage(
            "bot",
            data.message || "This specific information is not provided by any service provider.",
            chipsHtml({}, data.mcp_tool)
          );
          readyForNewQuestion();
          return;
        }

        if (data.error) {
          addMessage("bot error", data.error);
          readyForNewQuestion();
          return;
        }

        if (data.needs_clarification) {
          pendingRequest = requestText;
          awaitingField = data.field;
          addMessage(
            "bot",
            data.question,
            chipsHtml(data.interpreted_as, data.mcp_tool) + optionsHtml(data.options)
          );
          sendBtn.disabled = false;
          input.disabled = false;
          input.placeholder = (data.input && data.input.placeholder) || "Type your reply…";
          input.focus();
          return;
        }

        if (data.session_filters) {
          lastFilters = data.session_filters;
        }

        const shown = (data.packages || []).length;
        const matched = data.total_matched != null ? data.total_matched : data.total_results;
        const countText = matched > shown
          ? `Showing the top ${shown} of ${matched} current packages.`
          : `Ranked ${shown || 0} current package(s).`;
        const header = data.recommendation
          ? `Best match: ${data.recommendation.title || data.recommendation.provider}. ${countText}`
          : (shown ? countText : (data.message || "No packages found."));
        const notice = data.accuracy_notice
          ? `<div class="notice">${escapeHtml(data.accuracy_notice)}</div>`
          : "";
        addMessage(
          "bot",
          header,
          chipsHtml(data.interpreted_as, data.mcp_tool) + recommendationHtml(data.recommendation) + packagesHtml(data.packages) + comparisonHtml(data.comparison) + notice
        );
        readyForNewQuestion();
      } catch (err) {
        thinking.remove();
        addMessage("bot error", "Request failed: " + (err && err.message ? err.message : err));
        readyForNewQuestion();
      }
    }

    function cellSortValue(row, key, type) {
      const cell = row.querySelector(`[data-col="${key}"]`);
      if (!cell) return null;
      const raw = cell.getAttribute("data-sort");
      if (raw === "" || raw == null) return null;
      if (type === "number") {
        const number = Number(raw);
        return Number.isFinite(number) ? number : null;
      }
      return raw;
    }
    function sortCompareTable(button) {
      const table = button.closest("table");
      if (!table) return;
      const key = button.getAttribute("data-key");
      const type = button.getAttribute("data-type") || "text";
      let dir = "asc";
      if (table.getAttribute("data-sort-key") === key && table.getAttribute("data-sort-dir") === "asc") {
        dir = "desc";
      }
      table.setAttribute("data-sort-key", key);
      table.setAttribute("data-sort-dir", dir);
      table.querySelectorAll(".sort-btn").forEach((btn) => {
        btn.removeAttribute("aria-sort");
        const mark = btn.querySelector(".sort-ind");
        if (mark) mark.textContent = "↕";
      });
      button.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
      const mark = button.querySelector(".sort-ind");
      if (mark) mark.textContent = dir === "asc" ? "↑" : "↓";
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const sign = dir === "asc" ? 1 : -1;
      rows.sort((left, right) => {
        const a = cellSortValue(left, key, type);
        const b = cellSortValue(right, key, type);
        if (a == null && b == null) return 0;
        if (a == null) return 1;
        if (b == null) return -1;
        if (type === "number") return (a - b) * sign;
        return String(a).localeCompare(String(b), undefined, { numeric: true }) * sign;
      });
      rows.forEach((row) => tbody.appendChild(row));
    }
    function applyCompareFilters(wrap) {
      const provider = (wrap.querySelector('select[data-filter="provider"]') || {}).value || "";
      const international = (wrap.querySelector('select[data-filter="international"]') || {}).value || "";
      wrap.querySelectorAll("tbody tr").forEach((row) => {
        const okProvider = !provider || row.getAttribute("data-provider") === provider;
        const okIntl = !international || row.getAttribute("data-international") === international;
        row.hidden = !(okProvider && okIntl);
      });
    }

    thread.addEventListener("click", (event) => {
      const sortBtn = event.target.closest("button.sort-btn");
      if (sortBtn) {
        event.preventDefault();
        sortCompareTable(sortBtn);
        return;
      }
      const button = event.target.closest("button.option");
      if (!button) return;
      input.value = button.getAttribute("data-value") || "";
      form.requestSubmit();
    });
    thread.addEventListener("change", (event) => {
      const select = event.target.closest("select.compare-filter");
      if (!select) return;
      applyCompareFilters(select.closest(".compare-wrap"));
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      addMessage("user", text);
      input.value = "";
      if (/\\b(new search|start over|reset|clear session)\\b/i.test(text)) {
        lastFilters = null;
        seenBotTexts.clear();
      }
      const merged = mergeFollowUp(text);
      await runCompare(merged);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });

    addMessage(
      "bot",
      "Ask for current KSA tourist SIM packages (data, voice, or both). I will clarify trip length and budget, remember this chat, refuse unrelated topics, and check official operator websites only — not a live promo guarantee."
    );
  </script>
</body>
</html>
""".replace("__PORT__", str(PORT))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[web-agent] {self.address_string()} {fmt % args}")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code: int, html: str) -> None:
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._html(200, PAGE)
            return
        if self.path == "/api/status":
            self._json(200, {"source": "official_operator_websites"})
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/api/compare":
            self._json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "Invalid JSON"})
            return

        request = (data.get("request") or "").strip()
        prior = data.get("previous_filters")
        if not isinstance(prior, dict):
            prior = None
        if not request:
            self._json(400, {"error": "request is required"})
            return
        try:
            if is_off_topic(request) and not (prior and is_filter_follow_up(request)):
                result = call_mcp_tool(
                    "refuse_off_topic",
                    {"request": request},
                )
            else:
                arguments = {"request": request}
                if prior:
                    arguments["previous_filters"] = json.dumps(prior)
                result = call_mcp_tool(
                    "compare_sim_packages",
                    arguments,
                )
        except Exception as exc:
            self._json(500, {"error": str(exc)})
            return
        self._json(200, result)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"KSA SIM web agent: http://{HOST}:{PORT}/")
    print("This UI calls the MCP server over stdio (compare_sim_packages / refuse_off_topic).")
    server.serve_forever()


if __name__ == "__main__":
    main()
