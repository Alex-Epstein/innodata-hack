/* Shared helpers: data loading that works over http and from disk (file://), the score tally, answer checks. */
(function () {
  "use strict";
  const MODEL_NAMES = { haiku: "Claude Haiku 5.5", luna: "GPT-6 Luna" };
  const SHORT = { haiku: "Haiku", luna: "Luna" };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("could not load " + src));
      document.head.appendChild(s);
    });
  }

  async function getJSON(url) {
    if (location.protocol === "file:") throw new Error("file://");
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(url + ": " + r.status);
    return r.json();
  }

  async function loadIndex() {
    try { return await getJSON("data/index.json"); }
    catch (e) { await loadScript("data/index.js"); return window.BTA_INDEX; }
  }

  async function loadTask(id) {
    try { return await getJSON("data/" + encodeURIComponent(id) + ".json"); }
    catch (e) {
      return new Promise((resolve, reject) => {
        window.BTA_TASK = (t) => resolve(t);
        loadScript("data/" + encodeURIComponent(id) + ".js").catch(reject);
      });
    }
  }

  function norm(v) { return String(v == null ? "" : v).trim().toLowerCase(); }

  function isCorrect(task, value) {
    if (value == null || value === "") return false;
    if (task.answer_type === "integer" || task.answer_type === "number") {
      const a = Number(task.answer), b = Number(value);
      if (!isFinite(b)) return false;
      if (task.answer_type === "integer") return a === b;
      const tol = task.tolerance_abs != null ? task.tolerance_abs : (task.tolerance_rel || 0) * Math.abs(a);
      return Math.abs(a - b) <= tol;
    }
    return norm(task.answer) === norm(value);
  }

  /* Running tally, per browser. Every storage access is wrapped: private windows and blocked storage just skip it. */
  const KEY = "bta.v1";
  function readStore() {
    try { const s = JSON.parse(localStorage.getItem(KEY) || "{}"); return s && typeof s === "object" ? s : {}; }
    catch (e) { return {}; }
  }
  function writeStore(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* storage off */ } }
  function record(task, value, ok) {
    const s = readStore();
    s.played = s.played || {};
    s.played[task.task_id] = { you: value, ok: !!ok, haiku: !!(task.models.haiku || {}).correct,
                               luna: !!(task.models.luna || {}).correct, at: Date.now() };
    writeStore(s);
    return tally(s);
  }
  function tally(s) {
    s = s || readStore();
    const p = Object.values(s.played || {});
    return { n: p.length, you: p.filter((x) => x.ok).length, haiku: p.filter((x) => x.haiku).length,
             luna: p.filter((x) => x.luna).length };
  }
  function played(id) { const s = readStore(); return (s.played || {})[id] || null; }
  function resetTally() { writeStore({}); }

  function qs(name) { return new URLSearchParams(location.search).get(name); }
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
    return e;
  }
  function fmtAnswer(task, v) {
    if (v == null || v === "") return "—";
    if (task.template === "sunset") { const n = Number(v); return (n > 0 ? "+" : "") + n + " min"; }
    return String(v);
  }

  window.BTA = { MODEL_NAMES, SHORT, loadIndex, loadTask, loadScript, isCorrect, record, tally, played, resetTally,
                 qs, el, fmtAnswer };
})();
