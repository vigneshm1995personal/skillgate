const app = document.getElementById("app");
const banner = document.getElementById("banner");
const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MOTION_MS = 350;
const CHECKING_MIN_MS = 1400;
let meta = { account: false, demo_default: true, packs: [] };
let wizard = blankWizard();
let lastRoutePath = "";
let lastRun = { path: "", snap: null };

function blankWizard() {
  return {
    step: 1,
    dir: 1,
    path: "",
    name: "",
    description: "",
    body: "",
    license: "",
    stubFrom: "",
    existing: false,
    progress: { completed: 0, total: 0 },
    result: null,
  };
}

function $(html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = html.trim();
  return wrap.firstElementChild;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function prefersReducedMotion() {
  return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

async function api(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (!res.ok) {
    const err = new Error(data.error || res.statusText);
    err.status = res.status;
    err.payload = data;
    throw err;
  }
  return data;
}

function showError(err) {
  const hint = err.payload && err.payload.hint ? `<p class="muted">${esc(err.payload.hint)}</p>` : "";
  return `<p class="err">${esc(err.message)}</p>${hint}`;
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function packHref(packOrPath) {
  const value = typeof packOrPath === "string"
    ? packOrPath
    : (packOrPath.display_path || packOrPath.name || packOrPath.path);
  return `#/pack?path=${encodeURIComponent(value)}`;
}

function defaultDescription(name) {
  const n = name || "skill";
  return `Produce ${n} notes, extracts, and local file outputs. Use when the user asks for ${n}, mentions invoices or documents, or wants the documented ${n} workflow.`;
}

function checkerLabel(report, snap) {
  const name = String((report && report.harness) || "").toLowerCase();
  if (name === "demo" || (snap && snap.demo_notice)) return "Built-in checker";
  if (name === "llm") return "Your API key";
  if (name === "codex") return "Codex (your API key)";
  if (name === "cursor-agent") return "Cursor (your API key)";
  if (snap && snap.error) return "Your API key";
  return "";
}

function checkHeadline(task) {
  const id = String((task && task.id) || "");
  if (id.includes("no-trigger")) return "The skill should stay off for an unrelated request.";
  if (id.includes("should-trigger") || id.startsWith("trigger-")) {
    return "The skill should run for a matching request.";
  }
  const prompt = String((task && task.prompt) || "").replace(/\s+/g, " ").trim();
  if (prompt) {
    const cut = prompt.match(/^.+?[.?!](?=\s|$)/);
    let one = (cut && cut[0]) || prompt;
    if (one.length > 96) one = `${one.slice(0, 93).replace(/\s+\S*$/, "")}…`;
    if (!/[.?!]$/.test(one)) one += ".";
    return one;
  }
  const words = id.replace(/[-_]+/g, " ").trim();
  if (!words) return "This check should pass.";
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}.`;
}

function validateName(name) {
  const value = (name || "").trim();
  if (!value) return "Name your skill to continue.";
  if (value.length > 64) return "Use 1–64 characters.";
  if (!NAME_RE.test(value)) return "Use lowercase letters, numbers, and single hyphens.";
  return "";
}

function route() {
  const hash = location.hash.slice(1) || "/";
  const [path, qs] = hash.split("?");
  const params = new URLSearchParams(qs || "");
  return { path: path || "/", params };
}

async function boot() {
  meta = await api("GET", "/api/meta");
  if (meta.pack && !location.hash) {
    location.hash = `#/pack?path=${encodeURIComponent(meta.pack)}`;
  }
  render();
}

function render() {
  const { path, params } = route();
  if (path !== "/setup") {
    wizard = blankWizard();
  } else if (lastRoutePath !== "/setup" && !params.get("path")) {
    wizard = blankWizard();
  }
  lastRoutePath = path;
  if (path === "/setup") return renderSetup(params);
  if (path === "/pack") return renderPack(params);
  return renderPicker();
}

async function renderPicker() {
  const data = await api("GET", "/api/packs");
  const packs = data.packs || [];
  const example = packs.find((p) => p.green_demo);
  const red = packs.find((p) => p.red_demo);
  app.innerHTML = "";
  app.appendChild($(`<section>
    <h1>Create a skill or open one you have</h1>
    <p class="muted">No Skill Gate account. Run check uses the built-in checker — no API key needed.</p>
  </section>`));
  const choices = $(`<div class="choices"></div>`);
  const create = $(`<button type="button" class="choice" id="new-btn">
    <strong>Create a skill</strong>
    <span>Name it, describe it, and run a check. About two minutes. No API key.</span>
  </button>`);
  create.onclick = () => { wizard = blankWizard(); location.hash = "#/setup"; };
  choices.appendChild(create);
  if (example) {
    const tryEx = $(`<button type="button" class="choice" id="example-btn">
      <strong>Try an example</strong>
      <span>Open the pdf skill and run check. You should see a pass.</span>
    </button>`);
    tryEx.onclick = () => { location.hash = `${packHref(example)}&run=1`; };
    choices.appendChild(tryEx);
  }
  app.appendChild(choices);
  if (red) {
    const quiet = $(`<button type="button" class="choice quiet" id="red-path">
      <strong>See a failing check</strong>
      <span>Open a broken example, run check, then apply the suggested description on this same skill.</span>
    </button>`);
    quiet.onclick = () => { location.hash = `${packHref(red)}&run=1`; };
    app.appendChild(quiet);
  }
  const list = $(`<div class="card"><h2>Your skills</h2><div class="list"></div></div>`);
  const box = list.querySelector(".list");
  packs.forEach((p) => {
    const label = p.red_demo ? "Failing example" : p.green_demo ? `${p.name} · example` : p.name;
    const btn = $(`<button type="button" class="secondary">${esc(label)}</button>`);
    btn.onclick = () => { location.hash = packHref(p); };
    box.appendChild(btn);
  });
  if (!packs.length) box.innerHTML = "<p class='muted'>No skills yet.</p>";
  app.appendChild(list);
  const open = $(`<div class="card">
    <h2>Open a folder</h2>
    <label for="open-path">Path</label>
    <input id="open-path" placeholder="skills/pdf">
    <p><button type="button" id="open-btn">Open</button></p>
    <div id="open-err"></div>
  </div>`);
  open.querySelector("#open-btn").onclick = () => {
    const value = open.querySelector("#open-path").value.trim();
    if (!value) return;
    location.hash = `#/pack?path=${encodeURIComponent(value)}`;
  };
  app.appendChild(open);
}

function ensureWizardShell() {
  let root = document.getElementById("wiz-root");
  if (root) return root;
  app.innerHTML = "";
  root = $(`<div id="wiz-root">
    <div id="wiz-stepper"></div>
    <div id="wiz-stage"></div>
  </div>`);
  app.appendChild(root);
  return root;
}

function updateStepper(step) {
  const wrap = document.getElementById("wiz-stepper");
  if (!wrap) return;
  if (!wrap.querySelector(".stepper")) {
    wrap.innerHTML = `<div class="stepper" aria-label="Setup steps">
      <span class="node current" data-node="1">1</span>
      <span class="label">Name</span>
      <span class="rail"><i></i></span>
      <span class="node" data-node="2">2</span>
      <span class="label">Describe</span>
    </div>`;
  }
  const show = step === 1 || step === 2 || step === "checking";
  wrap.hidden = !show;
  if (!show) return;
  const one = wrap.querySelector("[data-node='1']");
  const two = wrap.querySelector("[data-node='2']");
  const rail = wrap.querySelector(".rail");
  const oneDone = step !== 1;
  const twoCurrent = step === 2;
  const twoDone = step === "checking" || step === "success" || step === "fail";
  one.className = "node " + (oneDone ? "done" : "current");
  one.textContent = oneDone ? "✓" : "1";
  two.className = "node " + (twoDone ? "done" : twoCurrent ? "current" : "");
  two.textContent = twoDone ? "✓" : "2";
  if (oneDone) {
    const fill = () => rail.classList.add("filled");
    if (prefersReducedMotion() || rail.classList.contains("filled")) fill();
    else requestAnimationFrame(() => requestAnimationFrame(fill));
  } else {
    rail.classList.remove("filled");
  }
}

function swapPanel(nextEl) {
  const stage = document.getElementById("wiz-stage");
  nextEl.classList.add("wiz-panel");
  const current = stage.querySelector(".wiz-panel:not(.panel-leave):not(.panel-leave-back)");
  const dirBack = wizard.dir < 0;
  if (!current || prefersReducedMotion()) {
    stage.innerHTML = "";
    if (current && prefersReducedMotion()) {
      stage.appendChild(nextEl);
      return Promise.resolve();
    }
    if (!prefersReducedMotion()) nextEl.classList.add(dirBack ? "panel-enter-back" : "panel-enter");
    stage.appendChild(nextEl);
    return Promise.resolve();
  }
  current.classList.remove("panel-enter", "panel-enter-back");
  current.classList.add(dirBack ? "panel-leave-back" : "panel-leave");
  nextEl.classList.add(dirBack ? "panel-enter-back" : "panel-enter");
  stage.appendChild(nextEl);
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      if (current.parentNode) current.remove();
      resolve();
    };
    current.addEventListener("animationend", done, { once: true });
    setTimeout(done, MOTION_MS + 40);
  });
}

function buildWizardPanel() {
  const step = wizard.step;
  if (step === 1) {
    const card = $(`<div class="card">
      <h2>Name your skill</h2>
      <label for="name">Name</label>
      <input id="name" value="${esc(wizard.name)}" autocomplete="off">
      <p class="field-msg" id="step-msg" aria-live="polite"></p>
      <p class="muted">Lowercase letters, numbers, and hyphens.</p>
      <p><button type="button" id="next">Continue</button></p>
    </div>`);
    const nameInput = card.querySelector("#name");
    const msg = card.querySelector("#step-msg");
    const go = () => {
      const name = nameInput.value.trim();
      const problem = validateName(name);
      if (problem) {
        msg.textContent = problem;
        nameInput.focus();
        return;
      }
      const prevStub = wizard.stubFrom ? defaultDescription(wizard.stubFrom) : "";
      if (!wizard.existing && (!wizard.description || wizard.description === prevStub)) {
        wizard.description = defaultDescription(name);
        wizard.stubFrom = name;
      }
      wizard.name = name;
      wizard.dir = 1;
      wizard.step = 2;
      paintWizard();
    };
    card.querySelector("#next").onclick = go;
    nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    nameInput.addEventListener("input", () => { msg.textContent = ""; });
    queueMicrotask(() => nameInput.focus());
    return card;
  }

  if (step === 2) {
    const primary = wizard.existing ? "Save and run check" : "Create and run check";
    const card = $(`<div class="card">
      <h2>What should it do?</h2>
      <p class="muted">${esc(wizard.name)}</p>
      <label for="sk-desc">Description</label>
      <textarea id="sk-desc">${esc(wizard.description || defaultDescription(wizard.name))}</textarea>
      <p class="field-msg" id="step-msg" aria-live="polite"></p>
      <p><button type="button" class="secondary" id="back">Back</button>
      <button type="button" id="next">${primary}</button></p>
    </div>`);
    const msg = card.querySelector("#step-msg");
    card.querySelector("#back").onclick = () => {
      wizard.description = card.querySelector("#sk-desc").value;
      if (wizard.existing && wizard.path) {
        location.hash = packHref(wizard.path);
        return;
      }
      wizard.dir = -1;
      wizard.step = 1;
      paintWizard();
    };
    card.querySelector("#next").onclick = () => {
      wizard.description = card.querySelector("#sk-desc").value.trim();
      if (!wizard.description) {
        msg.textContent = "Add a short description of what the skill does.";
        return;
      }
      createAndRun(card.querySelector("#next"));
    };
    return card;
  }

  if (step === "checking") {
    return $(`<div class="card">
      <h2>Checking…</h2>
      <div class="progress busy" id="wiz-progress"><i></i></div>
      <p class="muted" id="wiz-prog-label">Running your checks</p>
    </div>`);
  }

  const snap = wizard.result || {};
  const report = snap.report || {};
  const passed = report.passed_count ?? 0;
  const total = report.task_count ?? (report.tasks || []).length;
  const ok = step === "success" || snap.exit_code === 0;
  const card = ok
    ? $(`<div class="card success">
      <div class="check-pop" aria-hidden="true">
        <svg viewBox="0 0 72 72" role="img" aria-label="Passed">
          <circle cx="36" cy="36" r="32" fill="none" stroke="currentColor" stroke-width="3"></circle>
          <path d="M22 37 l10 10 18-22" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
        </svg>
      </div>
      <h1 class="gate green">Passed</h1>
      <p>${esc(passed)}/${esc(total)} checks</p>
      <p class="muted">Built-in checker. No API key needed.</p>
      <p><button type="button" class="secondary" id="see">See the checks</button></p>
    </div>`)
    : $(`<div class="card">
      <h1 class="gate red">Failed</h1>
      <p>${esc(passed)}/${esc(total)} checks</p>
      <p class="muted">Built-in checker. No API key needed.</p>
      <p><button type="button" id="see">See the checks</button></p>
    </div>`);
  const see = card.querySelector("#see");
  if (see) see.onclick = () => { location.hash = packHref(wizard.path); };
  return card;
}

async function paintWizard() {
  ensureWizardShell();
  updateStepper(wizard.step);
  await swapPanel(buildWizardPanel());
  const pop = document.querySelector("#wiz-stage .check-pop");
  if (pop && !prefersReducedMotion()) {
    pop.classList.remove("play");
    void pop.offsetWidth;
    pop.classList.add("play");
  } else if (pop) {
    pop.classList.add("play");
  }
}

async function renderSetup(params) {
  const incoming = params.get("path");
  if (incoming) {
    wizard.existing = true;
    if (incoming !== wizard.path || !wizard.name) {
      wizard.path = incoming;
      try {
        const pack = await api("GET", `/api/pack?path=${encodeURIComponent(wizard.path)}`);
        wizard.name = pack.skill.name;
        wizard.description = pack.skill.description;
        wizard.body = pack.skill.body || "";
        wizard.license = pack.skill.license || "";
      } catch (e) { /* keep going; step 1 can still create */ }
    }
    if (wizard.step === 1) wizard.step = 2;
  }
  const root = document.getElementById("wiz-root");
  if (root) root.remove();
  await paintWizard();
}

async function createAndRun(button) {
  button.disabled = true;
  wizard.dir = 1;
  wizard.step = "checking";
  wizard.progress = { completed: 0, total: 0 };
  const shownAt = Date.now();
  await paintWizard();
  try {
    if (!wizard.path) {
      const created = await api("POST", "/api/packs", {
        parent: "skills",
        name: wizard.name,
        description: wizard.description,
      });
      wizard.path = created.display_path || created.path;
      wizard.body = created.skill.body || "";
      if (wizard.description !== (created.skill.description || "")) {
        await api("PUT", "/api/pack/skill-md", {
          path: wizard.path,
          name: wizard.name,
          description: wizard.description,
          body: wizard.body,
        });
      }
    } else {
      await api("PUT", "/api/pack/skill-md", {
        path: wizard.path,
        name: wizard.name,
        description: wizard.description,
        body: wizard.body,
        license: wizard.license,
      });
    }
    const started = await api("POST", "/api/check", { path: wizard.path, live: false });
    await pollWizard(started.run_id);
    if (!prefersReducedMotion()) {
      const wait = CHECKING_MIN_MS - (Date.now() - shownAt);
      if (wait > 0) await sleep(wait);
      const bar = document.querySelector("#wiz-progress > i");
      const wrap = document.getElementById("wiz-progress");
      if (wrap) wrap.classList.remove("busy");
      if (bar) bar.style.width = "100%";
      await sleep(220);
    }
    wizard.step = (wizard.result && wizard.result.exit_code === 0) ? "success" : "fail";
    await paintWizard();
  } catch (e) {
    wizard.dir = -1;
    wizard.step = 2;
    await paintWizard();
    const msg = document.getElementById("step-msg");
    if (msg) msg.innerHTML = showError(e);
  }
}

async function pollWizard(runId) {
  for (;;) {
    const snap = await api("GET", `/api/runs/${runId}`);
    if (snap.exit_code === null || snap.exit_code === undefined) {
      const prog = snap.progress || {};
      wizard.progress = {
        completed: prog.completed_count || 0,
        total: prog.task_count || 0,
      };
      const wrap = document.getElementById("wiz-progress");
      const bar = wrap && wrap.querySelector("i");
      const label = document.getElementById("wiz-prog-label");
      const total = wizard.progress.total || 0;
      const done = wizard.progress.completed || 0;
      if (total && wrap) {
        wrap.classList.remove("busy");
        const pct = Math.max(12, Math.round((done / total) * 100));
        if (bar) bar.style.width = `${pct}%`;
        if (label) label.textContent = `${done}/${total} checks`;
      }
      await sleep(400);
      continue;
    }
    wizard.result = snap;
    lastRun = { path: wizard.path, snap };
    return;
  }
}

async function renderPack(params) {
  const path = params.get("path");
  if (!path) { location.hash = "#/"; return; }
  wizard.path = path;
  let pack;
  try { pack = await api("GET", `/api/pack?path=${encodeURIComponent(path)}`); }
  catch (e) { app.innerHTML = showError(e); return; }
  wizard.name = pack.skill.name;
  wizard.description = pack.skill.description;
  wizard.body = pack.skill.body || "";
  app.innerHTML = "";
  const head = $(`<section>
    <h1>${esc(pack.skill.name)}</h1>
    <p class="muted">${esc(pack.display_path || pack.skill.name)}</p>
    <p>${esc(pack.skill.description)}</p>
    <p class="muted">Run check uses the built-in checker. Run live uses your API key.</p>
    <p class="row">
      <button type="button" id="run">Run check</button>
      <button type="button" class="secondary" id="live">Run live</button>
      <a class="btn secondary" href="#/setup?path=${encodeURIComponent(path)}">Edit in wizard</a>
    </p>
    <details class="keys">
      <summary>Use your own API key (optional)</summary>
      <div class="stack">
        <p class="muted">Leave this closed. Run check does not need a key. A key is only for Run live.</p>
        <label>OpenAI</label><input id="k-openai" type="password" autocomplete="off">
        <label>Cursor</label><input id="k-cursor" type="password" autocomplete="off">
        <label>Codex</label><input id="k-codex" type="password" autocomplete="off">
        <label>Anthropic</label><input id="k-ant" type="password" autocomplete="off">
        <label>AI Gateway</label><input id="k-gw" type="password" autocomplete="off">
        <p><button type="button" class="secondary" id="save-key">Save key</button></p>
        <div id="key-err"></div>
      </div>
    </details>
    <div id="run-err"></div>
    <div id="results"></div>
  </section>`);
  head.querySelector("#run").onclick = () => startCheck(path, false);
  head.querySelector("#live").onclick = () => startCheck(path, true);
  head.querySelector("#save-key").onclick = async () => {
    const keyErr = head.querySelector("#key-err");
    const body = {
      OPENAI_API_KEY: head.querySelector("#k-openai").value,
      CURSOR_API_KEY: head.querySelector("#k-cursor").value,
      CODEX_API_KEY: head.querySelector("#k-codex").value,
      ANTHROPIC_API_KEY: head.querySelector("#k-ant").value,
      AI_GATEWAY_API_KEY: head.querySelector("#k-gw").value,
    };
    try {
      await api("PUT", "/api/env", body);
      keyErr.innerHTML = "<p class='muted'>Saved for Run live. Run check still uses the built-in checker.</p>";
    } catch (e) { keyErr.innerHTML = showError(e); }
  };
  app.appendChild(head);
  if (params.get("run") === "1") startCheck(path, false);
  else if (lastRun.path === path && lastRun.snap) paintResult(lastRun.snap, path);
}

async function startCheck(path, live) {
  const box = document.getElementById("results");
  const err = document.getElementById("run-err");
  err.innerHTML = "";
  box.innerHTML = `<div class="progress busy" id="run-progress"><i></i></div><p class="muted" id="run-prog-label">Running check…</p>`;
  banner.classList.add("hidden");
  try {
    const started = await api("POST", "/api/check", { path, live });
    await pollRun(started.run_id, path);
  } catch (e) {
    box.innerHTML = "";
    err.innerHTML = showError(e);
  }
}

async function pollRun(runId, path) {
  const box = document.getElementById("results");
  for (;;) {
    const snap = await api("GET", `/api/runs/${runId}`);
    if (snap.exit_code === null || snap.exit_code === undefined) {
      const prog = snap.progress || {};
      const total = prog.task_count || 0;
      const done = prog.completed_count || 0;
      const wrap = document.getElementById("run-progress");
      const bar = wrap && wrap.querySelector("i");
      const label = document.getElementById("run-prog-label");
      if (total && wrap) {
        wrap.classList.remove("busy");
        if (bar) bar.style.width = `${Math.max(12, Math.round((done / total) * 100))}%`;
        if (label) label.textContent = `${done}/${total} checks`;
      }
      await sleep(400);
      continue;
    }
    paintResult(snap, path);
    lastRun = { path, snap };
    return;
  }
}

function paintResult(snap, path) {
  const box = document.getElementById("results");
  const report = snap.report || {};
  if (snap.error && !snap.report) {
    const hint = snap.error.hint ? `<p class="muted">${esc(snap.error.hint)}</p>` : "";
    box.innerHTML = `<p class="err">${esc(snap.error.message || "Your API key could not run this check.")}</p>${hint}`;
    banner.classList.add("hidden");
    return;
  }
  const gate = (report.gate || (snap.exit_code === 0 ? "green" : "red")).toLowerCase();
  if (snap.demo_notice) {
    banner.textContent = snap.demo_notice;
    banner.classList.remove("hidden");
  }
  const tasks = report.tasks || [];
  const rows = tasks.map((t) => {
    const mark = t.passed ? "PASS" : "FAIL";
    const cls = t.passed ? "pass" : "fail";
    const why = (t.failures && t.failures[0]) || "";
    const extra = t.advice ? `<div class="muted">${esc(t.advice.why || "")}</div>` : "";
    return `<tr><td class="${cls}">${mark}</td><td>${esc(checkHeadline(t))}${extra}</td><td>${esc(why)}</td></tr>`;
  }).join("");
  const advice = report.advice;
  let adviceHtml = "";
  if (advice && gate === "red") {
    adviceHtml = `<div class="card">
      <h2>${esc(advice.headline || "Fix")}</h2>
      <p>${esc(advice.why || "")}</p>
      <p>${esc(advice.change || "")}</p>
      ${advice.demo_note ? `<p class="muted">${esc(advice.demo_note)}</p>` : ""}
      <p>Corrected description (not the current one):</p>
      <pre id="paste">${esc(advice.paste || advice.description || "")}</pre>
      <button type="button" id="apply">Apply description fix on this pack</button>
    </div>`;
  }
  const headline = gate === "green" ? "Passed" : "Failed";
  const checker = checkerLabel(report, snap);
  const checkerLine = checker === "Built-in checker"
    ? "Built-in checker. No API key needed."
    : checker;
  box.innerHTML = `
    <p><span class="gate ${esc(gate)}">${headline}</span>
      · ${esc(report.passed_count ?? 0)}/${esc(report.task_count ?? tasks.length)} checks</p>
    <p class="muted">${esc(checkerLine)}</p>
    <table><thead><tr><th>Result</th><th>Check</th><th>What happened</th></tr></thead><tbody>${rows}</tbody></table>
    ${adviceHtml}
  `;
  const apply = document.getElementById("apply");
  if (apply && advice) {
    apply.onclick = async () => {
      if (path.includes("skills/pdf-sabotaged") && !confirm("This edits the example skill in your checkout. Continue?")) return;
      try {
        await api("POST", "/api/pack/apply-advice", {
          path,
          description: advice.description || advice.paste,
        });
        startCheck(path, false);
      } catch (e) {
        box.insertAdjacentHTML("afterbegin", showError(e));
      }
    };
  }
}

window.addEventListener("hashchange", () => { render(); });
boot().catch((e) => { app.innerHTML = showError(e); });
