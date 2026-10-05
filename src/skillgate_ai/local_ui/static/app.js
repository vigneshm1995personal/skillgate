const app = document.getElementById("app");
const banner = document.getElementById("banner");
const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MOTION_MS = 350;
const CHECKING_MIN_MS = 700;
const SETUP_DONE_KEY = "skillgate-setup-done";
let meta = { account: false, demo_default: true, packs: [], has_any_key: false, pdf_path: null };
let wizard = blankWizard();
let lastRoutePath = "";
let lastRun = { path: "", snap: null };

function blankWizard() {
  return {
    step: "local",
    dir: 1,
    path: "",
    name: "",
    description: "",
    body: "",
    license: "",
    stubFrom: "",
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

function setupDone() {
  try { return localStorage.getItem(SETUP_DONE_KEY) === "1"; } catch { return false; }
}

function markSetupDone() {
  try { localStorage.setItem(SETUP_DONE_KEY, "1"); } catch { /* ignore */ }
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

function keyFieldsHtml() {
  return `<label>OpenAI</label><input id="k-openai" type="password" autocomplete="off">
        <label>Cursor</label><input id="k-cursor" type="password" autocomplete="off">
        <label>Codex</label><input id="k-codex" type="password" autocomplete="off">
        <label>Anthropic</label><input id="k-ant" type="password" autocomplete="off">
        <label>AI Gateway</label><input id="k-gw" type="password" autocomplete="off">`;
}

function keyPayloadFrom(root) {
  const fields = [
    ["OPENAI_API_KEY", "#k-openai"],
    ["CURSOR_API_KEY", "#k-cursor"],
    ["CODEX_API_KEY", "#k-codex"],
    ["ANTHROPIC_API_KEY", "#k-ant"],
    ["AI_GATEWAY_API_KEY", "#k-gw"],
  ];
  const body = {};
  fields.forEach(([name, sel]) => {
    const el = root.querySelector(sel);
    const value = el ? el.value.trim() : "";
    if (value) body[name] = value;
  });
  return body;
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

function onSetupFlow() {
  return ["local", "keys", "firstSkill", "name", "describe"].includes(wizard.step);
}

async function boot() {
  meta = await api("GET", "/api/meta");
  if (!location.hash) {
    if (meta.pack) {
      location.hash = `#/pack?path=${encodeURIComponent(meta.pack)}`;
    } else if (!setupDone()) {
      location.hash = "#/setup";
    }
  }
  render();
}

function render() {
  const { path, params } = route();
  if (path !== "/setup" && path !== "/new") {
    wizard = blankWizard();
  } else if (lastRoutePath !== path && lastRoutePath !== "/setup" && lastRoutePath !== "/new") {
    wizard = blankWizard();
    if (path === "/new") wizard.step = "name";
  }
  lastRoutePath = path;
  if (path === "/setup") return renderSetup(params);
  if (path === "/new") return renderNew();
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
    <p class="muted">No Skill Gate account. Run live uses your API key.</p>
  </section>`));
  const choices = $(`<div class="choices"></div>`);
  const create = $(`<button type="button" class="choice" id="new-btn">
    <strong>Create a skill</strong>
    <span>Name it, describe it, then run live on the skill page.</span>
  </button>`);
  create.onclick = () => { wizard = blankWizard(); wizard.step = "name"; location.hash = "#/new"; };
  choices.appendChild(create);
  if (example) {
    const tryEx = $(`<button type="button" class="choice" id="example-btn">
      <strong>Try an example</strong>
      <span>Open the pdf skill. Run live from the skill page.</span>
    </button>`);
    tryEx.onclick = () => { location.hash = packHref(example); };
    choices.appendChild(tryEx);
  }
  app.appendChild(choices);
  if (red) {
    const quiet = $(`<button type="button" class="choice quiet" id="red-path">
      <strong>See a failing check</strong>
      <span>Open a broken example, then run live on that skill page.</span>
    </button>`);
    quiet.onclick = () => { location.hash = packHref(red); };
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

function swapIn(stage, nextEl, dir, panelClass) {
  if (!stage) return Promise.resolve();
  nextEl.classList.add(panelClass);
  const current = stage.querySelector(`.${panelClass}:not(.panel-leave):not(.panel-leave-back)`);
  const dirBack = dir < 0;
  if (!current || prefersReducedMotion()) {
    stage.innerHTML = "";
    stage.appendChild(nextEl);
    return Promise.resolve();
  }
  current.classList.remove("panel-enter", "panel-enter-back");
  void current.offsetWidth;
  current.classList.add(dirBack ? "panel-leave-back" : "panel-leave");
  nextEl.classList.add(dirBack ? "panel-enter-back" : "panel-enter");
  stage.appendChild(nextEl);
  return sleep(MOTION_MS).then(() => {
    if (current.parentNode) current.remove();
  });
}

function swapPanel(nextEl) {
  return swapIn(document.getElementById("wiz-stage"), nextEl, wizard.dir, "wiz-panel");
}

function updateStepper(step) {
  const wrap = document.getElementById("wiz-stepper");
  if (!wrap) return;
  if (!wrap.querySelector(".stepper")) {
    wrap.innerHTML = `<div class="stepper" aria-label="Setup steps">
      <span class="node current" data-node="1">1</span>
      <span class="label">Local</span>
      <span class="rail"><i></i></span>
      <span class="node" data-node="2">2</span>
      <span class="label">Key</span>
    </div>`;
  }
  const show = step === "local" || step === "keys";
  const one = wrap.querySelector("[data-node='1']");
  const two = wrap.querySelector("[data-node='2']");
  const rail = wrap.querySelector(".rail");
  const oneDone = step !== "local";
  const twoCurrent = step === "keys";
  const twoDone = step === "firstSkill" || step === "name" || step === "describe";
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
  wrap.hidden = !show;
}

async function paintWizard() {
  ensureWizardShell();
  updateStepper(wizard.step);
  await swapPanel(buildWizardPanel());
  const wrap = document.getElementById("wiz-stepper");
  const show = wizard.step === "local" || wizard.step === "keys";
  if (wrap) wrap.hidden = !show;
}

function goFirstSkill() {
  markSetupDone();
  wizard.dir = 1;
  wizard.step = "firstSkill";
  paintWizard();
}

function buildWizardPanel() {
  const step = wizard.step;
  if (step === "local") {
    const card = $(`<div class="card">
      <h2>This is local</h2>
      <p>Skill Gate runs on this computer. No Skill Gate account.</p>
      <p class="muted">Your API key is the model that runs live checks. Skip only if you want the built-in checker.</p>
      <p><button type="button" id="next">Continue</button></p>
    </div>`);
    card.querySelector("#next").onclick = () => {
      wizard.dir = 1;
      wizard.step = "keys";
      paintWizard();
    };
    return card;
  }

  if (step === "keys") {
    if (meta.has_any_key) {
      const have = $(`<div class="card">
        <h2>Your API key</h2>
        <p class="muted">You already have an API key. Live checks will use it.</p>
        <p><button type="button" id="next">Continue</button></p>
      </div>`);
      have.querySelector("#next").onclick = () => goFirstSkill();
      return have;
    }
    const form = $(`<div class="card">
      <h2>Your API key</h2>
      <p class="muted">Cursor, Codex, Claude, OpenAI, or AI Gateway. This is the model that runs live checks. No Skill Gate account.</p>
      ${keyFieldsHtml()}
      <p class="field-msg" id="step-msg" aria-live="polite"></p>
      <p><button type="button" id="save-key">Save key</button>
      <button type="button" class="secondary" id="skip">Skip — use the built-in checker</button></p>
      <p class="muted">Skip is the only way onto the built-in checker. That is not a live model.</p>
      <div id="key-err"></div>
    </div>`);
    form.querySelector("#skip").onclick = () => goFirstSkill();
    form.querySelector("#save-key").onclick = async () => {
      const msg = form.querySelector("#step-msg");
      const keyErr = form.querySelector("#key-err");
      const body = keyPayloadFrom(form);
      if (!Object.keys(body).length) {
        msg.textContent = "Add a key to save, or skip to use the built-in checker.";
        return;
      }
      try {
        const saved = await api("PUT", "/api/env", body);
        meta.has_any_key = !!(saved && saved.has_any_key);
        goFirstSkill();
      } catch (e) { keyErr.innerHTML = showError(e); }
    };
    return form;
  }

  if (step === "firstSkill") {
    const pdf = meta.pdf_path;
    const card = $(`<div class="card">
      <h2>Want to add your first skill?</h2>
      <p class="muted">You run checks on the skill page, not here.</p>
      <p><button type="button" id="yes">Yes</button>
      ${pdf ? `<button type="button" class="secondary" id="pdf">Try the pdf example</button>` : ""}
      <button type="button" class="secondary" id="later">Not now</button></p>
    </div>`);
    card.querySelector("#yes").onclick = () => {
      wizard.dir = 1;
      wizard.step = "name";
      paintWizard();
    };
    const pdfBtn = card.querySelector("#pdf");
    if (pdfBtn) {
      pdfBtn.onclick = () => { location.hash = packHref(pdf); };
    }
    card.querySelector("#later").onclick = () => { location.hash = "#/"; };
    return card;
  }

  if (step === "name") {
    const card = $(`<div class="card">
      <h2>Name your skill</h2>
      <label for="name">Name</label>
      <input id="name" value="${esc(wizard.name)}" autocomplete="off">
      <p class="field-msg" id="step-msg" aria-live="polite"></p>
      <p class="muted">Lowercase letters, numbers, and hyphens.</p>
      <p><button type="button" class="secondary" id="back">Back</button>
      <button type="button" id="next">Continue</button></p>
    </div>`);
    const nameInput = card.querySelector("#name");
    const msg = card.querySelector("#step-msg");
    card.querySelector("#back").onclick = () => {
      wizard.name = nameInput.value.trim();
      wizard.dir = -1;
      if (lastRoutePath === "/new") {
        location.hash = "#/";
        return;
      }
      wizard.step = "firstSkill";
      paintWizard();
    };
    const go = () => {
      const name = nameInput.value.trim();
      const problem = validateName(name);
      if (problem) {
        msg.textContent = problem;
        nameInput.focus();
        return;
      }
      const prevStub = wizard.stubFrom ? defaultDescription(wizard.stubFrom) : "";
      if (!wizard.description || wizard.description === prevStub) {
        wizard.description = defaultDescription(name);
        wizard.stubFrom = name;
      }
      wizard.name = name;
      wizard.dir = 1;
      wizard.step = "describe";
      paintWizard();
    };
    card.querySelector("#next").onclick = go;
    nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    nameInput.addEventListener("input", () => { msg.textContent = ""; });
    queueMicrotask(() => nameInput.focus());
    return card;
  }

  const card = $(`<div class="card">
    <h2>What should it do?</h2>
    <p class="muted">${esc(wizard.name)}</p>
    <label for="sk-desc">Description</label>
    <textarea id="sk-desc">${esc(wizard.description || defaultDescription(wizard.name))}</textarea>
    <p class="field-msg" id="step-msg" aria-live="polite"></p>
    <p><button type="button" class="secondary" id="back">Back</button>
    <button type="button" id="next">Create skill</button></p>
  </div>`);
  const msg = card.querySelector("#step-msg");
  card.querySelector("#back").onclick = () => {
    wizard.description = card.querySelector("#sk-desc").value;
    wizard.dir = -1;
    wizard.step = "name";
    paintWizard();
  };
  card.querySelector("#next").onclick = () => {
    wizard.description = card.querySelector("#sk-desc").value.trim();
    if (!wizard.description) {
      msg.textContent = "Add a short description of what the skill does.";
      return;
    }
    createSkill(card.querySelector("#next"));
  };
  return card;
}

async function renderSetup(params) {
  const incoming = params.get("path");
  if (incoming) {
    location.hash = packHref(incoming);
    return;
  }
  if (setupDone() && !onSetupFlow()) {
    location.hash = "#/";
    return;
  }
  if (setupDone() && wizard.step === "local") {
    location.hash = "#/";
    return;
  }
  const root = document.getElementById("wiz-root");
  if (root) root.remove();
  await paintWizard();
}

async function renderNew() {
  if (wizard.step !== "name" && wizard.step !== "describe") {
    wizard = blankWizard();
    wizard.step = "name";
  }
  const root = document.getElementById("wiz-root");
  if (root) root.remove();
  await paintWizard();
}

async function createSkill(button) {
  button.disabled = true;
  try {
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
    location.hash = packHref(wizard.path);
  } catch (e) {
    button.disabled = false;
    const msg = document.getElementById("step-msg");
    if (msg) msg.innerHTML = showError(e);
  }
}

function checksFromPack(pack) {
  const cases = (pack.dataset && pack.dataset.cases) || [];
  return cases.map((item) => ({ id: item.id, prompt: item.prompt }));
}

function checksTable(tasks) {
  const rows = tasks.map((t) => `<tr><td>${esc(checkHeadline(t))}</td></tr>`).join("");
  if (!rows) return `<p class="muted">No checks yet.</p>`;
  return `<table><thead><tr><th>Check</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function setRunButtonsDisabled(disabled) {
  const live = document.getElementById("live");
  const builtin = document.getElementById("builtin");
  if (live) live.disabled = disabled;
  if (builtin) builtin.disabled = disabled;
}

function checkingLine(opts) {
  if (opts && opts.live && !opts.demo) return "Run live uses your API key.";
  return "Built-in checker. This is not a live model.";
}

function checkingPanel(opts) {
  return $(`<div>
    <p class="gate">Checking</p>
    <div class="progress busy" id="run-progress"><i></i></div>
    <p class="muted" id="run-prog-label">Running your checks</p>
    <p class="muted">${esc(checkingLine(opts))}</p>
  </div>`);
}

async function showChecking(opts) {
  const stage = document.getElementById("run-stage");
  if (!stage) return;
  await swapIn(stage, checkingPanel(opts), 1, "run-panel");
}

function resultMarkHtml(ok, complete) {
  const label = ok ? "Passed" : "Failed";
  const cls = ["check-pop", ok ? "" : "fail", complete ? "complete" : ""].filter(Boolean).join(" ");
  const d = ok ? "M22 37 l10 10 18-22" : "M24 24 L48 48 M48 24 L24 48";
  return `<div class="${cls}" aria-hidden="true">
    <svg viewBox="0 0 72 72" role="img" aria-label="${label}">
      <circle cx="36" cy="36" r="32" fill="none" stroke="currentColor" stroke-width="3"></circle>
      <path d="${d}" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
    </svg>
  </div>`;
}

async function playMark(pop) {
  if (!pop) return;
  if (prefersReducedMotion()) {
    pop.classList.add("complete");
    pop.classList.remove("play");
    return;
  }
  pop.classList.remove("play", "complete");
  void pop.offsetWidth;
  await new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        pop.classList.add("play");
        resolve();
      });
    });
  });
}

async function revealResult(panel, replay) {
  const stage = document.getElementById("run-stage");
  if (!stage) return;
  const pop = panel.querySelector(".check-pop");
  if (!replay || prefersReducedMotion()) {
    if (pop) {
      pop.classList.add("complete");
      pop.classList.remove("play");
    }
    stage.innerHTML = "";
    panel.classList.add("run-panel");
    stage.appendChild(panel);
    return;
  }
  await swapIn(stage, panel, 1, "run-panel");
  await playMark(stage.querySelector(".check-pop"));
}

async function renderPack(params) {
  const path = params.get("path");
  if (!path) { location.hash = "#/"; return; }
  wizard.path = path;
  try { meta = await api("GET", "/api/meta"); } catch (e) { /* keep cached meta */ }
  let pack;
  try { pack = await api("GET", `/api/pack?path=${encodeURIComponent(path)}`); }
  catch (e) { app.innerHTML = showError(e); return; }
  wizard.name = pack.skill.name;
  wizard.description = pack.skill.description;
  wizard.body = pack.skill.body || "";
  app.innerHTML = "";
  const hasKey = !!meta.has_any_key;
  const keyLine = hasKey
    ? "Run live uses your API key."
    : "Built-in checker. This is not a live model.";
  const head = $(`<section>
    <h1>${esc(pack.skill.name)}</h1>
    <p class="muted">${esc(pack.display_path || pack.skill.name)}</p>
    <p>${esc(pack.skill.description)}</p>
    <p class="muted">${esc(keyLine)}</p>
    <p class="row">
      <button type="button" id="live">Run live</button>
      ${hasKey ? "" : `<button type="button" class="secondary" id="builtin">Run with built-in checker</button>`}
    </p>
    <details class="keys">
      <summary>${hasKey ? "Replace your API key" : "Add your API key"}</summary>
      <div class="stack">
        ${keyFieldsHtml()}
        <p><button type="button" class="secondary" id="save-key">Save key</button></p>
        <div id="key-err"></div>
      </div>
    </details>
    <h2>Checks</h2>
    <div id="run-err"></div>
    <div id="results"><div id="run-stage"></div></div>
  </section>`);
  head.querySelector("#live").onclick = () => startCheck(path, { live: true });
  const builtin = head.querySelector("#builtin");
  if (builtin) builtin.onclick = () => startCheck(path, { live: false, demo: true });
  head.querySelector("#save-key").onclick = async () => {
    const keyErr = head.querySelector("#key-err");
    const body = keyPayloadFrom(head);
    if (!Object.keys(body).length) {
      keyErr.innerHTML = "<p class='muted'>Add a key to save.</p>";
      return;
    }
    try {
      const saved = await api("PUT", "/api/env", body);
      meta.has_any_key = !!(saved && saved.has_any_key);
      keyErr.innerHTML = "<p class='muted'>Saved. Run live uses your API key.</p>";
      renderPack(params);
    } catch (e) { keyErr.innerHTML = showError(e); }
  };
  app.appendChild(head);
  const stage = document.getElementById("run-stage");
  if (lastRun.path === path && lastRun.snap) {
    await paintResult(lastRun.snap, path, { replay: false });
  } else if (stage) {
    const idle = $(`<div>${checksTable(checksFromPack(pack))}</div>`);
    idle.classList.add("run-panel");
    stage.appendChild(idle);
  }
}

async function startCheck(path, opts) {
  const err = document.getElementById("run-err");
  const stage = document.getElementById("run-stage");
  err.innerHTML = "";
  banner.classList.add("hidden");
  const body = { path, live: !!opts.live };
  if (opts.demo) body.demo = true;
  setRunButtonsDisabled(true);
  try {
    const started = await api("POST", "/api/check", body);
    await showChecking(opts);
    await pollRun(started.run_id, path, Date.now());
  } catch (e) {
    if (stage) stage.innerHTML = "";
    err.innerHTML = showError(e);
  } finally {
    setRunButtonsDisabled(false);
  }
}

async function pollRun(runId, path, checkingShownAt) {
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
    const wait = prefersReducedMotion()
      ? 0
      : Math.max(0, CHECKING_MIN_MS - (Date.now() - checkingShownAt));
    if (wait > 0) await sleep(wait);
    await paintResult(snap, path, { replay: true });
    lastRun = { path, snap, runId };
    return;
  }
}

async function paintResult(snap, path, opts) {
  const replay = !!(opts && opts.replay);
  const report = snap.report || {};
  if (snap.error && !snap.report) {
    const hint = snap.error.hint ? `<p class="muted">${esc(snap.error.hint)}</p>` : "";
    const panel = $(`<div><p class="err">${esc(snap.error.message || "Your API key could not run this check.")}</p>${hint}</div>`);
    banner.classList.add("hidden");
    await revealResult(panel, replay);
    return;
  }
  const gate = (report.gate || (snap.exit_code === 0 ? "green" : "red")).toLowerCase();
  if (snap.demo_notice) {
    banner.textContent = snap.demo_notice;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
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
    ? "Built-in checker. This is not a live model."
    : checker;
  const complete = !replay || prefersReducedMotion();
  const panel = $(`<div>
    <div class="run-stamp success">
      ${resultMarkHtml(gate === "green", complete)}
      <p><span class="gate ${esc(gate)}">${headline}</span>
        · ${esc(report.passed_count ?? 0)}/${esc(report.task_count ?? tasks.length)} checks</p>
      <p class="muted">${esc(checkerLine)}</p>
    </div>
    <table><thead><tr><th>Result</th><th>Check</th><th>What happened</th></tr></thead><tbody>${rows}</tbody></table>
    ${adviceHtml}
  </div>`);
  const apply = panel.querySelector("#apply");
  if (apply && advice) {
    apply.onclick = async () => {
      if (path.includes("skills/pdf-sabotaged") && !confirm("This edits the example skill in your checkout. Continue?")) return;
      try {
        await api("POST", "/api/pack/apply-advice", {
          path,
          description: advice.description || advice.paste,
        });
        if (meta.has_any_key) startCheck(path, { live: true });
        else startCheck(path, { live: false, demo: true });
      } catch (e) {
        panel.insertAdjacentHTML("afterbegin", showError(e));
      }
    };
  }
  await revealResult(panel, replay);
}

window.addEventListener("hashchange", () => { render(); });
boot().catch((e) => { app.innerHTML = showError(e); });
