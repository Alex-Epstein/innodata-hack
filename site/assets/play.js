/* Play (2D, fair) -> reveal (3D, the truth on the mountain). ?t=<task_id>, ?intro=1 for the projector flyover,
   ?timer=<seconds>. Keys: digits / Enter to answer, Space shows the answer, F fullscreen, R restarts. */
(async function () {
  "use strict";
  const { el, qs } = BTA;
  const $ = (id) => document.getElementById(id);
  const mapbox = $("mapbox"), img = $("map2d");
  const show = qs("show") === "1";                       // the auto tour for the pitch (press S)
  const tourStep = Number(qs("i") || 0);
  const intro = qs("intro") === "1" || (show && tourStep === 0 && qs("intro") !== "0");
  let stage = null, task = null, index = null, answered = false, timerId = null, value = "";

  function frameRect() {                                  // the map frame of the PNG, in mapbox pixels
    const cw = mapbox.clientWidth, ch = mapbox.clientHeight;
    const [iw, ih] = task.image_size;
    const s = Math.min(cw / iw, ch / ih), ox = (cw - iw * s) / 2, oy = (ch - ih * s) / 2;
    const f = task.frame_px;
    return { x0: ox + f[0] * s, y0: oy + f[1] * s, x1: ox + f[2] * s, y1: oy + f[3] * s };
  }

  function caption(text, on) {
    const c = $("caption");
    c.querySelector("span").textContent = text || "";
    c.classList.toggle("on", !!on);
  }

  // the tour: the opening flood, then one map per mission that stumped both models
  function tour(ix) {
    const out = [ix.featured];
    const bothWrong = (x) => Object.values(x.models).length === 2 && Object.values(x.models).every((m) => !m.correct);
    for (const tpl of ["crossings", "sunset", "los", "flood"]) {
      const c = ix.tasks.filter((x) => x.template === tpl && x.has3d && !out.includes(x.task_id));
      const pick = c.find(bothWrong) || c.find((x) => Object.values(x.models).some((m) => !m.correct));
      if (pick && out.length < 5) out.push(pick.task_id);
    }
    return out.filter(Boolean);
  }

  // ------------------------------------------------------------------ load
  try {
    index = await BTA.loadIndex();
    const id = (show ? tour(index)[tourStep % tour(index).length] : null) || qs("t") || index.featured || (index.tasks[0] || {}).task_id;
    task = await BTA.loadTask(id);
  } catch (e) {
    $("prompt").textContent = "Could not load this task. Run scripts/build-site first.";
    console.warn(e);
    return;
  }
  document.title = `Beat the AI · ${task.title}`;
  $("place").textContent = [task.title, task.area].filter(Boolean).join(" · ");
  $("coord").textContent = task.seed != null ? `seed ${task.seed} · ${task.generator_version || ""}` : "";
  $("kicker").textContent = task.title;
  $("taskId").textContent = task.task_id;
  $("prompt").textContent = task.prompt;
  $("fullq").textContent = task.question;
  $("sheetImg").src = task.image;

  const loader = $("loader");
  let loaderTick = null;
  if (intro && task.has3d) {
    loader.classList.remove("hidden");
    $("loaderTitle").textContent = (task.area || "Surveying").split(",")[0];
    $("loaderWhere").textContent = "Reading the elevation model";
    const top = Math.round(task.grid.zmax), t0 = performance.now();
    loaderTick = setInterval(() => {
      const p = Math.min(1, (performance.now() - t0) / 2200);
      const e = 1 - Math.pow(1 - p, 3);
      $("loaderElev").textContent = `${Math.round(top * e)} m`;
      $("loaderBar").style.width = `${e * 100}%`;
    }, 40);
  }

  img.src = task.image;                                   // the answer buttons do not wait for the image

  // the 3D stage loads in the background; the answer buttons work right away
  const stageReady = !task.has3d ? Promise.resolve(null) : BTAStage.create(mapbox, task, { frameRect })
    .then((s) => { s.showTop(); stage = s; window.BTA_STAGE = s; return s; })
    .catch((e) => { console.warn("3D stage unavailable, using the 2D reveal:", e); return null; });

  // ------------------------------------------------------------------ answer input
  const answers = $("answers");
  function submit(v) {
    if (answered) return;
    answered = true;
    reveal(v);
  }
  if (task.options && task.options.length) {
    answers.className = "answers" + (task.options.length === 2 || task.options.length === 4 ? " two" : "");
    task.options.forEach((o, i) => {
      answers.append(el("button", { class: "ans", type: "button", "data-k": String(i + 1),
                                    onclick: (ev) => { ev.currentTarget.classList.add("picked"); submit(o); } }, o));
    });
    $("hint").textContent = "Tap your answer. You see exactly what the models saw.";
  } else {
    answers.className = "numpad";
    const disp = el("div", { class: "display" }, el("span", { class: "ph" }, "your number"));
    const go = el("button", { class: "ans go", type: "button", disabled: true, onclick: () => submit(value) }, "Lock it in");
    const paint = () => {
      disp.innerHTML = "";
      disp.append(value === "" ? el("span", { class: "ph" }, "your number") : value + (task.template === "sunset" ? " min" : ""));
      go.disabled = value === "" || value === "-";
    };
    const press = (k) => {
      if (answered) return;
      if (k === "del") value = value.slice(0, -1);
      else if (k === "-") value = value.startsWith("-") ? value.slice(1) : "-" + value;
      else if (value.replace("-", "").length < 4) value = (value === "0" ? "" : value) + k;
      paint();
    };
    answers.append(disp);
    for (const k of ["1", "2", "3", "4", "5", "6", "7", "8", "9"]) answers.append(el("button", { class: "ans key", type: "button", onclick: () => press(k) }, k));
    const neg = task.template === "sunset";
    answers.append(el("button", { class: "ans key", type: "button", onclick: () => press(neg ? "-" : "del"), "aria-label": neg ? "plus or minus" : "delete" }, neg ? "±" : "⌫"));
    answers.append(el("button", { class: "ans key", type: "button", onclick: () => press("0") }, "0"));
    answers.append(el("button", { class: "ans key", type: "button", onclick: () => press("del"), "aria-label": "delete" }, neg ? "⌫" : "C"));
    answers.append(go);
    $("hint").textContent = task.template === "sunset"
      ? "Minutes to spare before sunset; use ± for after dark."
      : "Type your count. You see exactly what the models saw.";
    answers.press = press;
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (ev.key === "f" || ev.key === "F") {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen && document.documentElement.requestFullscreen().catch(() => {});
      else document.exitFullscreen && document.exitFullscreen();
      return;
    }
    if (ev.key === "r" || ev.key === "R") { location.href = show ? "play.html?show=1" : location.href; if (!show) location.reload(); return; }
    if (ev.key === "s" || ev.key === "S") { location.href = show ? "./" : "play.html?show=1"; return; }
    if (show) return;
    if (answered) return;
    if (ev.key === " ") { ev.preventDefault(); submit(null); return; }
    if (answers.press) {
      if (/^[0-9]$/.test(ev.key)) answers.press(ev.key);
      else if (ev.key === "-") answers.press("-");
      else if (ev.key === "Backspace") answers.press("del");
      else if (ev.key === "Enter" && value !== "" && value !== "-") submit(value);
    } else if (/^[1-9]$/.test(ev.key)) {
      const b = answers.querySelector(`[data-k="${ev.key}"]`);
      if (b) b.click();
    }
  });

  $("zoomBtn").addEventListener("click", () => { $("sheet").classList.remove("hidden"); });
  $("sheetClose").addEventListener("click", () => { $("sheet").classList.add("hidden"); });

  // ------------------------------------------------------------------ timer
  function startTimer(secs) {
    const t0 = performance.now();
    const tick = () => {
      const left = Math.max(0, secs - (performance.now() - t0) / 1000);
      $("timerT").textContent = String(Math.ceil(left));
      $("timerBar").style.width = `${(left / secs) * 100}%`;
      $("timer").classList.toggle("low", left <= 10);
      if (left <= 0 && !answered) { answered = true; reveal(null, true); }
    };
    tick();
    timerId = setInterval(tick, 200);
  }

  // ------------------------------------------------------------------ intro (projector)
  async function runIntro() {
    img.style.opacity = "0";
    document.body.classList.add("stage-on");
    if (loaderTick) {
      await BTAStage.sleep(1200);
      clearInterval(loaderTick);
      $("loaderElev").textContent = `${Math.round(task.grid.zmax)} m`;
      $("loaderBar").style.width = "100%";
      await BTAStage.sleep(350);
    }
    const lock = $("lockup");
    const go = stage.intro({
      ms: 8000,
      onStart: () => { loader.classList.add("done"); setTimeout(() => lock.classList.add("in"), 500); },
      onProgress: (p) => { if (p > 0.62 && !lock.classList.contains("out")) lock.classList.add("out"); },
      onDescend: () => { lock.classList.add("out"); },
    });
    await go;
    document.body.classList.remove("stage-on");
    img.style.opacity = "1";
    await BTAStage.sleep(300);
    caption("This is what the AI sees.", true);
    await BTAStage.sleep(3200);
    caption("", false);
  }

  if (intro) { try { await img.decode(); } catch (e) { /* drawn when ready */ } await stageReady; }
  if (intro && stage) {
    $("panel").style.visibility = "hidden";
    await runIntro();
    $("panel").style.visibility = "";
  } else {
    loader.classList.add("done");
  }
  if (show) {
    $("playArea").classList.add("hidden");
    document.body.classList.add("show");
    if (!intro) { caption("This is what the AI sees.", true); }
    await BTAStage.sleep(intro ? 2000 : 3200);
    caption("", false);
    answered = true;
    await reveal(null, false);
    await BTAStage.sleep(task.template === "flood" ? 5500 : 4500);
    const n = tour(index).length;
    location.href = tourStep + 1 < n ? `play.html?show=1&i=${tourStep + 1}` : "factory.html?show=1";
    return;
  }
  const secs = Number(qs("timer")) || (intro ? 10 : 60);
  startTimer(secs);

  // ------------------------------------------------------------------ reveal
  async function reveal(you, timedOut) {
    clearInterval(timerId);
    const ok = BTA.isCorrect(task, you);
    const t = show ? BTA.tally() : BTA.record(task, you, ok);
    $("playArea").classList.add("hidden");
    $("resultArea").classList.remove("hidden");
    renderScore(you, ok, timedOut, t);
    $("zoomBtn").classList.add("hidden");
    await stageReady;
    if (stage) {
      stage.showTop();
      document.body.classList.add("stage-on");
      await BTAStage.sleep(80);
      img.style.opacity = "0";
      await BTAStage.sleep(450);
      img.style.visibility = "hidden";
      caption("This is the mountain.", true);
      setTimeout(() => caption("", false), 2600);
      await stage.reveal(you);
    } else {
      reveal2D(you);
    }
  }

  function renderScore(you, ok, timedOut, t) {
    const m = task.models || {};
    const fmt = (v) => BTA.fmtAnswer(task, v);
    const row = (cls, who, name, val, good) => el("div", { class: "row " + cls },
      el("span", { class: "who" }, who),
      el("span", { class: "val" }, fmt(val), name ? el("span", { class: "name" }, name) : null),
      good == null ? el("span", { class: "mark" }, "") : el("span", { class: "mark " + (good ? "ok" : "no") }, good ? "✓" : "✗"));
    const sc = $("score");
    sc.innerHTML = "";
    sc.append(el("h2", { class: "caps" }, "You vs the models"));
    sc.append(row("truth", "Truth", "computed from the data", task.answer, null));
    if (!show) sc.append(row("you", "You", timedOut ? "time ran out" : you == null ? "no answer" : "", you, ok));
    for (const k of ["haiku", "luna"]) {
      if (m[k]) sc.append(row("model", BTA.SHORT[k], BTA.MODEL_NAMES[k], m[k].parsed, m[k].correct));
    }
    const hk = m.haiku && m.haiku.correct, ln = m.luna && m.luna.correct;
    let v;
    if (show) v = !hk && !ln ? "Both models missed it." : hk && ln ? "Both models got this one." : `${hk ? "Haiku" : "Luna"} got it; ${hk ? "Luna" : "Haiku"} didn't.`;
    else if (ok && !hk && !ln) v = "You beat both models.";
    else if (ok && hk && ln) v = "You got it, and so did both models.";
    else if (ok) v = `You got it. ${hk ? "Haiku" : "Luna"} did too; ${hk ? "Luna" : "Haiku"} didn't.`;
    else if (!hk && !ln) v = { flood: "Nobody got this one. Watch where the water really goes.", crossings: "Nobody got this one. Count along the trail.",
      sunset: "Nobody got this one. Walk it with the hiker.", los: "Nobody got this one. Follow the sight line." }[task.template] || "Nobody got this one.";
    else v = `${hk && ln ? "Both models" : hk ? "Haiku" : "Luna"} got this one. Look at the mountain.`;
    $("verdict").textContent = v;
    const st = $("steps");
    st.innerHTML = "";
    for (const [k, val] of stepLines()) st.append(el("li", {}, k + " ", el("span", { class: "mono" }, val)));
    $("tally").innerHTML = "";
    $("tally").append(el("span", {}, "Your tally"), el("span", {}, "You ", el("b", {}, `${t.you}/${t.n}`)),
      el("span", {}, "Haiku ", el("b", {}, `${t.haiku}/${t.n}`)), el("span", {}, "Luna ", el("b", {}, `${t.luna}/${t.n}`)));
    const models = ["haiku", "luna"].filter((k) => m[k]).map((k) => m[k].model).join(" and ");
    $("fine").textContent = `The answer is computed from the elevation data by code, never by a model (generator ${task.generator_version || "?"}, seed ${task.seed}). ` +
      (models ? `Model answers: ${models}, temperature 0, reasoning effort high, parsed from their replies.` : "");
    const list = index.tasks.map((x) => x.task_id);
    const i = list.indexOf(task.task_id);
    const nxt = list.slice(i + 1).concat(list.slice(0, i)).find((id) => !BTA.played(id)) || list[(i + 1) % list.length];
    $("nextBtn").href = `play.html?t=${encodeURIComponent(nxt)}`;
  }

  function stepLines() {
    const s = task.steps || {};
    const out = [];
    if (task.template === "flood" && s.camps) {
      if (s.dam_elev_m != null) out.push(["Dam elevation", `${s.dam_elev_m} m`]);
      if (s.water_route_length_m != null) out.push(["Water route, steepest descent", `${s.water_route_length_m} m`]);
      const hit = s.camps.find((c) => c.flooded);
      if (hit) out.push([`${hit.camp} sits on the route at`, `${hit.elev_m} m`]);
      const near = s.camps.filter((c) => !c.flooded).sort((a, b) => a.distance_to_water_route_m - b.distance_to_water_route_m)[0];
      if (near) out.push([`Closest dry camp (${near.camp}) is off the route by`, `${near.distance_to_water_route_m} m`]);
    } else if (task.template === "crossings") {
      if (s.contour_crossings != null) out.push(["Contour lines crossed", `${s.contour_crossings} (${s.uphill} up, ${s.downhill} down)`]);
      if (s.trail_length_m != null) out.push(["Trail length", `${s.trail_length_m} m`]);
      if (s.levels_crossed) out.push(["Levels, in order", s.levels_crossed.join(" ")]);
    } else if (task.template === "sunset") {
      if (s.uphill_contour_crossings != null) out.push(["Uphill lines crossed", `${s.uphill_contour_crossings} → +${s.minutes_for_ascent} min`]);
      if (s.flat_walk_min != null) out.push(["Walking time", `${s.flat_walk_min} + ${s.minutes_for_ascent} = ${s.walking_minutes} min`]);
      if (s.daylight_minutes != null) out.push(["Daylight left", `${s.daylight_minutes} min`]);
      if (s.arrival) out.push(["Arrives", s.arrival]);
      if (s.wrong_if_every_crossing_counted != null && s.wrong_if_every_crossing_counted !== task.answer) out.push(["If you count downhill lines too", `${s.wrong_if_every_crossing_counted} min`]);
    } else if (task.template === "los") {
      if (s.distance_m != null) out.push(["Distance R to H", `${s.distance_m} m`]);
      if (s.terrain_at_critical_m != null) out.push(["Ground at the critical point", `${s.terrain_at_critical_m} m`]);
      if (s.sightline_at_critical_m != null) out.push(["Sight line there", `${s.sightline_at_critical_m} m`]);
      if (s.min_clearance_m != null) out.push(["Clearance", `${s.min_clearance_m} m`]);
    } else {
      for (const [k, v] of Object.entries(s)) {
        if (typeof v === "number" || typeof v === "string" || typeof v === "boolean") out.push([k.replace(/_/g, " "), String(v)]);
        if (out.length >= 5) break;
      }
    }
    return out;
  }

  // 2D reveal: the truth overlay image if the family made one, else the overlay geometry drawn over the map
  function reveal2D(you) {
    if (task.truth_image) { img.src = task.truth_image; return; }
    if (!task.scene || !task.frame_px) return;
    const [iw, ih] = task.image_size, f = task.frame_px, g = task.grid;
    const P = (p) => [f[0] + (p[0] / (g.cols - 1)) * (f[2] - f[0]), f[1] + (p[1] / (g.rows - 1)) * (f[3] - f[1])];
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "overlay2d");
    svg.setAttribute("viewBox", `0 0 ${iw} ${ih}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    for (const p of task.scene.paths || []) {
      if (p.role.startsWith("option_")) continue;
      const pl = document.createElementNS(NS, "polyline");
      pl.setAttribute("points", p.pts.map((q) => P(q).join(",")).join(" "));
      pl.setAttribute("fill", "none");
      pl.setAttribute("stroke", "#2F7FC1");
      pl.setAttribute("stroke-width", "7");
      pl.setAttribute("stroke-linejoin", "round");
      pl.setAttribute("opacity", "0.9");
      svg.append(pl);
    }
    for (const c of task.scene.crossings || []) {
      const ci = document.createElementNS(NS, "circle");
      const [x, y] = P(c.g);
      ci.setAttribute("cx", x); ci.setAttribute("cy", y); ci.setAttribute("r", 9);
      ci.setAttribute("fill", "none"); ci.setAttribute("stroke", "#2F7FC1"); ci.setAttribute("stroke-width", 3);
      svg.append(ci);
    }
    const pick = (name, color) => {
      const p = (task.scene.points || []).find((q) => q.name.toUpperCase() === String(name).toUpperCase());
      if (!p) return;
      const [x, y] = P(p.g);
      const ci = document.createElementNS(NS, "circle");
      ci.setAttribute("cx", x); ci.setAttribute("cy", y); ci.setAttribute("r", 30);
      ci.setAttribute("fill", "none"); ci.setAttribute("stroke", color); ci.setAttribute("stroke-width", 6);
      svg.append(ci);
    };
    for (const k of ["haiku", "luna"]) if (task.models[k] && !task.models[k].correct) pick(task.models[k].parsed, "#D2412C");
    pick(task.answer, "#2F7FC1");
    mapbox.append(svg);
  }
})();
