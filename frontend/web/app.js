/* Jarvis Command Center - client. Vanilla JS, no build step. */
(() => {
  const $ = (id) => document.getElementById(id);
  const messages = $("messages"), input = $("input"), orb = $("orb"), wave = $("wave"), mic = $("mic");
  const voiceMode = $("voiceMode"), voiceOut = $("voiceOut"), wakeWord = $("wakeWord");
  const replyLang = $("replyLang"), micLang = $("micLang"), voiceEn = $("voiceEn"), voiceHi = $("voiceHi"), rate = $("rate");
  let ws, state = {}, speaking = false, listening = false, recognition = null, logLines = [];
  const prefs = JSON.parse(localStorage.getItem("jarvis.prefs") || "{}");

  // ---------- clock ----------
  const tick = () => {
    const d = new Date();
    $("clockTime").textContent = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    $("clockDate").textContent = d.toLocaleDateString("en-IN", { weekday: "long", day: "2-digit", month: "long", year: "numeric" }).toUpperCase();
  };
  tick(); setInterval(tick, 10000);

  // ---------- views ----------
  function showView(name) {
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
    document.querySelectorAll(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.view === name));
  }
  document.querySelectorAll("[data-view]").forEach(el => el.addEventListener("click", () => showView(el.dataset.view)));

  // ---------- websocket ----------
  function connect() {
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = () => setSys("OPTIMAL", "");
    ws.onclose = () => { setSys("OFFLINE", "off"); setTimeout(connect, 2000); };
    ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  }
  function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }
  function setSys(text, cls) { $("sysStatus").textContent = text; $("sysDot").className = "dot " + (cls || ""); }

  function handle(m) {
    switch (m.type) {
      case "hello":
        messages.innerHTML = "";
        (m.history || []).forEach(h => addMsg(h.role, h.text));
        if (m.greeting) { addMsg("jarvis", m.greeting); speak(m.greeting, "en"); }
        renderState(m.state); break;
      case "user": addMsg("user", m.text); break;
      case "thinking": $("thinking").classList.remove("hidden"); orb.classList.add("busy"); $("coreState").textContent = "Thinking"; break;
      case "reply": $("thinking").classList.add("hidden"); orb.classList.remove("busy"); addMsg("jarvis", m.text); $("langTag").textContent = (m.lang || "en").toUpperCase(); speak(m.speak || m.text, m.lang || "en"); break;
      case "state": renderState(m.state); break;
      case "log": appendLog(m.line); break;
      case "run_started": addMsg("system", "▶ Started " + m.agent.replace("_", " ")); refreshState(); break;
      case "run_finished": addMsg("system", "■ Finished " + m.agent.replace("_", " ") + (m.code ? " (exit " + m.code + ")" : "")); refreshState(); break;
      case "needs_human": showHuman(m.reason); refreshState(); break;
    }
  }
  function refreshState() { send({ type: "state" }); }

  // ---------- chat ----------
  function addMsg(role, text) {
    const d = document.createElement("div");
    d.className = "msg " + role; d.textContent = text;
    messages.appendChild(d); messages.scrollTop = messages.scrollHeight;
  }
  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = input.value.trim(); if (!t) return;
    input.value = ""; send({ type: "chat", text: t });
  });
  document.querySelectorAll("[data-action]").forEach(b => b.addEventListener("click", () => {
    if (b.dataset.action === "start_applying" && !confirm("Start applying to all PENDING rows now?")) return;
    send({ type: "action", name: b.dataset.action });
  }));
  $("btnContinue").addEventListener("click", () => { send({ type: "action", name: "continue_run" }); hideHuman(); });
  $("refreshBtn").addEventListener("click", refreshState);
  $("resetBrain").addEventListener("click", () => { messages.innerHTML = ""; send({ type: "reset_brain" }); });

  function showHuman(reason) {
    $("humanReason").textContent = reason || "Check the browser window, fix what LinkedIn is asking for, then continue.";
    $("humanBanner").classList.remove("hidden");
    speak("I need your help in the browser. " + (reason || "") + " Say continue, or press the button, when you're done.", "en");
  }
  function hideHuman() { $("humanBanner").classList.add("hidden"); }

  // ---------- state rendering ----------
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function badge(t, cls) { return t ? `<span class="badge ${esc(cls || t)}">${esc(t)}</span>` : ""; }
  function resumeType(r) { return /mern/i.test(r) ? "mern" : /java/i.test(r) ? "java" : ""; }

  function renderState(s) {
    state = s || {};
    const run = state.run || {}, jobs = state.jobs || [], conns = state.connections || [], totals = state.totals || {};
    // chips / agents
    const chipRun = $("chipRun");
    if (run.waiting_for_human) { chipRun.textContent = "needs you"; chipRun.className = "chip human"; setSys("ACTION REQUIRED", "busy"); }
    else if (run.running) { chipRun.textContent = run.agent === "job_search" ? "searching jobs…" : "applying…"; chipRun.className = "chip run"; setSys("RUNNING", "busy"); hideHuman(); }
    else { chipRun.textContent = "idle"; chipRun.className = "chip"; setSys("OPTIMAL", ""); hideHuman(); }
    const b = state.brain || {};
    $("chipBrain").textContent = b.available ? "brain: " + b.model : "brain: offline";
    $("brainSub").textContent = b.available ? "Claude Code · " + b.model : "not found";
    setAgent("agBrain", b.available ? "online" : "offline", b.available ? "ok" : "");
    setAgent("agJobSearch", run.running && run.agent === "job_search" ? (run.waiting_for_human ? "needs you" : "running") : "idle", run.running && run.agent === "job_search" ? (run.waiting_for_human ? "human" : "running") : "");
    setAgent("agApply", run.running && run.agent === "apply" ? (run.waiting_for_human ? "needs you" : "running") : "idle", run.running && run.agent === "apply" ? (run.waiting_for_human ? "human" : "running") : "");
    $("miniLog").textContent = (run.last_lines || []).length ? run.last_lines.join("\n") : (logLines.length ? logLines.slice(-12).join("\n") : "No run yet.");
    $("miniLog").scrollTop = $("miniLog").scrollHeight;
    if (!speaking && !listening) $("coreState").textContent = run.running ? "Working" : "Standing by";
    document.querySelectorAll("[data-action]").forEach(btn => { const a = btn.dataset.action; btn.disabled = (a === "stop_run") ? !run.running : run.running; });
    if (state.prefs && state.prefs.reply_language) replyLang.value = state.prefs.reply_language;
    // stats
    const sent = conns.filter(c => /^SENT/.test(c.result)).length;
    $("stTotal").textContent = jobs.length; $("stPending").textContent = totals.PENDING || 0;
    $("stDone").textContent = totals.COMPLETED || 0; $("stPaused").textContent = (totals.PAUSED || 0) + (totals.FAILED || 0);
    $("stSent").textContent = sent;
    $("navJobs").textContent = jobs.length; $("navConns").textContent = conns.length;
    $("sysInfo").innerHTML = `Brain: <b>${esc(b.available ? b.model : "offline")}</b><br>Jobs in sheet: <b>${jobs.length}</b> · Requests logged: <b>${conns.length}</b><br>Voice mode: <b>${voiceMode.checked ? "on" : "off"}</b> · Mic language: <b>${micLang.value}</b>`;
    renderJobsMini(jobs); renderJobsTable(); renderConns(conns);
  }
  function setAgent(id, text, cls) { const el = $(id); el.className = "agent " + (cls || ""); el.querySelector(".ag-state").textContent = text; }

  function renderJobsMini(jobs) {
    const el = $("jobsMini");
    el.innerHTML = jobs.length ? "" : '<div class="msg system">No jobs yet — say "Jarvis, run a job search".</div>';
    jobs.slice(-6).reverse().forEach(j => {
      const c = document.createElement("div"); c.className = "card";
      c.innerHTML = `<h4>${esc(j.title || "(untitled)")}</h4><div class="meta"><span>${esc(j.company || "")}</span><span>${esc(j.location || "")}</span>${badge(j.status)}${badge(resumeType(j.resume))}</div><div class="desc">${esc(j.description || "No description saved.")}</div>`;
      c.addEventListener("click", () => c.classList.toggle("open"));
      el.appendChild(c);
    });
  }
  function renderJobsTable() {
    const q = ($("jobSearch").value || "").toLowerCase(), st = $("jobFilter").value, rt = $("resumeFilter").value;
    const tb = $("jobsTable").querySelector("tbody"); tb.innerHTML = "";
    (state.jobs || []).filter(j => (!st || j.status === st) && (!rt || resumeType(j.resume) === rt) && (!q || (j.title + " " + j.company + " " + j.location).toLowerCase().includes(q)))
      .forEach(j => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${j.excel_row}</td><td><b>${esc(j.title || "—")}</b></td><td>${esc(j.company || "—")}</td><td>${esc(j.location || "")}</td>
          <td>${badge(resumeType(j.resume))} <span class="err" style="color:var(--muted)">${esc(j.resume)}</span></td><td>${badge(j.status)}</td><td>${esc(j.application || "")}</td>
          <td>${j.hr_sent}</td><td>${j.dev_sent}</td><td class="err">${esc(j.error || "")}${(j.problems || []).length ? " invalid: " + esc(j.problems.join("; ")) : ""}</td>
          <td><a href="${esc(j.job_link)}" target="_blank" rel="noopener">job</a>${j.company_link ? ` · <a href="${esc(j.company_link)}" target="_blank" rel="noopener">company</a>` : ""}</td>`;
        tb.appendChild(tr);
      });
    if (!tb.children.length) tb.innerHTML = '<tr><td colspan="11" style="color:var(--muted)">No rows match.</td></tr>';
  }
  ["jobSearch", "jobFilter", "resumeFilter"].forEach(id => $(id).addEventListener("input", renderJobsTable));
  function renderConns(list) {
    const tb = $("connsTable").querySelector("tbody"); tb.innerHTML = "";
    list.forEach(c => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${esc(c.at)}</td><td>${c.row}</td><td>${badge(c.category)}</td><td>${esc(c.name || "?")}</td><td>${esc(c.headline || "")}</td><td>${badge(c.result)}</td><td><a href="${esc(c.url)}" target="_blank" rel="noopener">profile</a></td>`;
      tb.appendChild(tr);
    });
    if (!list.length) tb.innerHTML = '<tr><td colspan="7" style="color:var(--muted)">No connection requests yet.</td></tr>';
  }
  function appendLog(line) {
    logLines.push(line); if (logLines.length > 600) logLines.shift();
    $("log").textContent = logLines.join("\n"); $("log").scrollTop = $("log").scrollHeight;
    $("miniLog").textContent = logLines.slice(-12).join("\n"); $("miniLog").scrollTop = $("miniLog").scrollHeight;
  }

  // ---------- voice out ----------
  const synth = window.speechSynthesis;
  function voices() { return synth ? synth.getVoices() : []; }
  function pickVoice(lang) {
    const all = voices();
    const saved = prefs[lang === "hi" ? "voiceHi" : "voiceEn"];
    if (saved) { const v = all.find(v => v.name === saved); if (v) return v; }
    const pref = lang === "hi"
      ? [/hi-IN.*Natural/i, /Swara|Madhur/i, /hi-IN|hi_IN/i]
      : [/en-IN.*Natural|Neerja|Prabhat/i, /Natural.*en-(GB|US|AU)|Ryan|Sonia|Aria|Guy|Libby|Jenny/i, /Google UK English (Male|Female)/i, /Google US English/i, /en-IN/i, /^en/i];
    for (const re of pref) { const v = all.find(v => re.test(v.name + " " + v.lang)); if (v) return v; }
    return null;
  }
  function fillVoiceSelects() {
    const all = voices(); if (!all.length) return;
    const fill = (sel, filter, key) => {
      sel.innerHTML = '<option value="">Auto (best available)</option>';
      all.filter(filter).forEach(v => { const o = document.createElement("option"); o.value = v.name; o.textContent = `${v.name} (${v.lang})`; sel.appendChild(o); });
      sel.value = prefs[key] || "";
    };
    fill(voiceEn, v => /^en/i.test(v.lang), "voiceEn");
    fill(voiceHi, v => /^hi/i.test(v.lang), "voiceHi");
  }
  if (synth) { synth.onvoiceschanged = fillVoiceSelects; fillVoiceSelects(); }
  function speak(text, lang) {
    if (!voiceOut.checked || !synth || !text) return;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const v = pickVoice(lang); if (v) u.voice = v;
    u.lang = lang === "hi" ? "hi-IN" : (v && v.lang) || "en-IN";
    u.rate = parseFloat(rate.value) || 1; u.pitch = 0.95;
    u.onstart = () => { speaking = true; orb.classList.add("speaking"); wave.className = "wave speak"; $("coreState").textContent = "Speaking"; $("sideStatus").textContent = "Speaking"; if (listening) pauseListening(true); };
    u.onend = u.onerror = () => { speaking = false; orb.classList.remove("speaking"); wave.className = "wave"; $("coreState").textContent = "Standing by"; $("sideStatus").textContent = voiceMode.checked ? "Listening" : "Idle"; if (voiceMode.checked) setTimeout(startListening, 250); };
    synth.speak(u);
  }
  $("testVoice").addEventListener("click", () => speak(replyLang.value === "hi" ? "नमस्ते जोएल, मैं जार्विस हूँ। आज हम कौन सी jobs देखें?" : "Hello Joel, Jarvis here. Systems are online and ready.", replyLang.value));

  // ---------- voice in ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { mic.disabled = true; voiceMode.disabled = true; $("sideStatus").textContent = "Voice needs Chrome/Edge"; }
  let restartTimer = null;
  function startListening() {
    if (!SR || listening || speaking) return;
    recognition = new SR();
    recognition.lang = micLang.value || "en-IN";
    recognition.continuous = voiceMode.checked;
    recognition.interimResults = false;
    recognition.onresult = (ev) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        if (!ev.results[i].isFinal) continue;
        let text = ev.results[i][0].transcript.trim();
        if (!text) continue;
        if (voiceMode.checked && wakeWord.checked) {
          const m = text.match(/^(?:hi|hey|ok|okay|hello|हाय|हे|ओके)?\s*(?:jarvis|जार्विस)[,.!?]?\s*(.*)$/i);
          if (!m) continue;
          text = m[1].trim() || "hello";
        }
        send({ type: "chat", text });
      }
    };
    recognition.onend = () => {
      listening = false; mic.classList.remove("on"); orb.classList.remove("listening"); wave.className = "wave";
      if (voiceMode.checked && !speaking) { clearTimeout(restartTimer); restartTimer = setTimeout(startListening, 300); }
      else { $("sideStatus").textContent = "Idle"; }
    };
    recognition.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") { voiceMode.checked = false; addMsg("system", "Microphone access was denied — allow it in the browser address bar."); }
    };
    try { recognition.start(); listening = true; mic.classList.add("on"); orb.classList.add("listening"); wave.className = "wave on"; $("sideStatus").textContent = "Listening"; $("coreState").textContent = "Listening"; }
    catch (_) { listening = false; }
  }
  function pauseListening(temp) {
    clearTimeout(restartTimer);
    if (recognition) { try { recognition.onend = null; recognition.abort(); } catch (_) {} }
    listening = false; mic.classList.remove("on"); orb.classList.remove("listening"); wave.className = "wave";
    if (!temp) $("sideStatus").textContent = "Idle";
  }
  mic.addEventListener("click", () => { if (listening) { voiceMode.checked = false; pauseListening(); } else startListening(); });
  voiceMode.addEventListener("change", () => { savePrefs(); if (voiceMode.checked) startListening(); else pauseListening(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && voiceMode.checked && !listening && !speaking) startListening(); });

  // ---------- prefs ----------
  function savePrefs() {
    Object.assign(prefs, { voiceMode: voiceMode.checked, voiceOut: voiceOut.checked, wakeWord: wakeWord.checked, micLang: micLang.value, voiceEn: voiceEn.value, voiceHi: voiceHi.value, rate: rate.value });
    localStorage.setItem("jarvis.prefs", JSON.stringify(prefs));
  }
  [voiceOut, wakeWord, micLang, voiceEn, voiceHi, rate].forEach(el => el.addEventListener("change", savePrefs));
  micLang.addEventListener("change", () => { if (listening) { pauseListening(true); startListening(); } });
  replyLang.addEventListener("change", () => send({ type: "set_language", lang: replyLang.value }));
  (function loadPrefs() {
    if (prefs.voiceOut !== undefined) voiceOut.checked = prefs.voiceOut;
    if (prefs.wakeWord !== undefined) wakeWord.checked = prefs.wakeWord;
    if (prefs.micLang) micLang.value = prefs.micLang;
    if (prefs.rate) rate.value = prefs.rate;
    if (prefs.voiceMode) { voiceMode.checked = true; setTimeout(startListening, 800); }
  })();

  connect();
})();
