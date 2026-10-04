const app = document.getElementById("app");
const banner = document.getElementById("banner");
let meta = { account: false, demo_default: true, packs: [] };
let wizard = { step: 1, path: "", name: "", parent: "", description: "", body: "", license: "", evalMode: "scaffold" };

function $(html) {
  const wrap = document.createElement("div");
  wrap.innerHTML = html.trim();
  return wrap.firstElementChild;
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

function checkerLabel(report, snap) {
  const name = String((report && report.harness) || "").toLowerCase();
  if (name === "demo" || (snap && snap.demo_notice)) return "Built-in checker";
  if (name === "llm") return "Your API key";
  if (name === "codex") return "Codex (your API key)";
  if (name === "cursor-agent") return "Cursor (your API key)";
  if (snap && snap.error) return "Your API key";
  return "";
}
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
  if (path === "/setup") return renderSetup(params);
  if (path === "/pack") return renderPack(params);
  return renderPicker();
}

async function renderPicker() {
  const data = await api("GET", "/api/packs");
  const packs = data.packs || [];
  const red = packs.find((p) => p.red_demo);
  app.innerHTML = "";
  app.appendChild($(`<section>
    <h1>Pick or create a skill pack</h1>
    <p class="muted">No Skill Gate account. Run check uses the built-in checker — no API key needed.</p>
  </section>`));
  if (red) {
    const card = $(`<div class="card">
      <h2>See a red gate (no account)</h2>
      <p>Open <code>pdf-sabotaged</code>, run check, then apply the corrected description on <strong>this same pack</strong>.</p>
      <button type="button" id="red-path">Open sabotaged pack</button>
    </div>`);
    card.querySelector("#red-path").onclick = () => {
      location.hash = `${packHref(red)}&run=1`;
    };
    app.appendChild(card);
  }
  const list = $(`<div class="card"><h2>Your packs</h2><div class="list"></div></div>`);
  const box = list.querySelector(".list");
  packs.forEach((p) => {
    const btn = $(`<button type="button" class="secondary">${esc(p.name)}${p.red_demo ? " · red demo" : ""}${p.green_demo ? " · green demo" : ""}</button>`);
    btn.onclick = () => { location.hash = packHref(p); };
    box.appendChild(btn);
  });
  if (!packs.length) box.innerHTML = "<p class='muted'>No SKILL.md folders yet.</p>";
  app.appendChild(list);
  const open = $(`<div class="card">
    <h2>Open a folder</h2>
    <label for="open-path">Path</label>
    <input id="open-path" placeholder="skills/pdf">
    <p><button type="button" id="open-btn">Open</button>
    <button type="button" class="secondary" id="new-btn">Create a new pack</button></p>
    <div id="open-err"></div>
  </div>`);
  open.querySelector("#open-btn").onclick = () => {
    const value = open.querySelector("#open-path").value.trim();
    if (!value) return;
    location.hash = `#/pack?path=${encodeURIComponent(value)}`;
  };
  open.querySelector("#new-btn").onclick = () => { location.hash = "#/setup"; };
  app.appendChild(open);
}

async function renderSetup(params) {
  if (params.get("path")) wizard.path = params.get("path");
  if (wizard.path && !wizard.name) {
    try {
      const pack = await api("GET", `/api/pack?path=${encodeURIComponent(wizard.path)}`);
      wizard.name = pack.skill.name;
      wizard.description = pack.skill.description;
      wizard.body = pack.skill.body || "";
      wizard.license = pack.skill.license || "";
    } catch (e) { /* keep going; step 1 can still create */ }
  }
  const step = wizard.step;
  app.innerHTML = "";
  app.appendChild($(`<div class="steps">
    <span class="${step === 1 ? "on" : ""}">1 Folder</span>
    <span class="${step === 2 ? "on" : ""}">2 SKILL.md</span>
    <span class="${step === 3 ? "on" : ""}">3 Evals</span>
    <span class="${step === 4 ? "on" : ""}">4 Optional key</span>
  </div>`));
  const err = $(`<div id="wiz-err"></div>`);
  app.appendChild(err);
  if (step === 1) {
    const card = $(`<div class="card">
      <h2>Folder name = skill name</h2>
      <label>Parent directory</label>
      <input id="parent" value="${esc(wizard.parent || "skills")}">
      <label>Name (lowercase, hyphens)</label>
      <input id="name" value="${esc(wizard.name)}">
      <p class="muted">Rename the folder or the <code>name</code> field so they match.</p>
      <button type="button" id="next">Create / continue</button>
    </div>`);
    card.querySelector("#next").onclick = async () => {
      wizard.parent = card.querySelector("#parent").value.trim();
      wizard.name = card.querySelector("#name").value.trim();
      try {
        if (!wizard.path) {
          const created = await api("POST", "/api/packs", {
            parent: wizard.parent,
            name: wizard.name,
            scaffold: false,
          });
          wizard.path = created.display_path || created.path;
          wizard.description = created.skill.description;
          wizard.body = created.skill.body;
        }
        wizard.step = 2;
        render();
      } catch (e) { err.innerHTML = showError(e); }
    };
    app.appendChild(card);
    return;
  }
  if (step === 2) {
    const card = $(`<div class="card">
      <h2>SKILL.md frontmatter</h2>
      <label>Name (locked to folder)</label>
      <input id="sk-name" value="${esc(wizard.name)}" readonly>
      <label>Description</label>
      <textarea id="sk-desc">${esc(wizard.description)}</textarea>
      <label>Body (markdown)</label>
      <textarea id="sk-body">${esc(wizard.body)}</textarea>
      <label>License (optional)</label>
      <input id="sk-lic" value="${esc(wizard.license)}">
      <p><button type="button" class="secondary" id="back">Back</button>
      <button type="button" id="next">Save and next</button></p>
    </div>`);
    card.querySelector("#back").onclick = () => { wizard.step = 1; render(); };
    card.querySelector("#next").onclick = async () => {
      wizard.description = card.querySelector("#sk-desc").value;
      wizard.body = card.querySelector("#sk-body").value;
      wizard.license = card.querySelector("#sk-lic").value;
      try {
        const saved = await api("PUT", "/api/pack/skill-md", {
          path: wizard.path,
          name: wizard.name,
          description: wizard.description,
          body: wizard.body,
          license: wizard.license,
        });
        if (!saved.description_usable && saved.description_hint) {
          err.innerHTML = `<p class="muted">${esc(saved.description_hint)}</p>`;
        }
        wizard.step = 3;
        render();
      } catch (e) { err.innerHTML = showError(e); }
    };
    app.appendChild(card);
    return;
  }
  if (step === 3) {
    const clone = meta.pdf_path
      ? `<label><input type="radio" name="eval" value="clone"> Clone pdf demo layout (needs scripts for completion checks)</label>`
      : "";
    const card = $(`<div class="card">
      <h2>Evals</h2>
      <label><input type="radio" name="eval" value="existing"> Use existing evals/cases.yaml</label>
      <label><input type="radio" name="eval" value="scaffold" checked> Scaffold trigger-only checks (no API key, no scripts required)</label>
      ${clone}
      <p><button type="button" class="secondary" id="pdfs">Ensure demo PDFs</button></p>
      <p><button type="button" class="secondary" id="back">Back</button>
      <button type="button" id="next">Save evals</button></p>
    </div>`);
    card.querySelector("#back").onclick = () => { wizard.step = 2; render(); };
    card.querySelector("#pdfs").onclick = async () => {
      try {
        await api("POST", "/api/pack/fixtures", { path: wizard.path, ensure_demo_pdfs: true });
        err.innerHTML = "<p class='muted'>Wrote demo PDFs under evals/fixtures/ if missing.</p>";
      } catch (e) { err.innerHTML = showError(e); }
    };
    card.querySelector("#next").onclick = async () => {
      const mode = card.querySelector("input[name=eval]:checked").value;
      try {
        if (mode === "scaffold") {
          await api("POST", "/api/pack/scaffold", { path: wizard.path });
        } else if (mode === "clone") {
          const name = wizard.name || wizard.path.split("/").pop();
          const created = await api("POST", "/api/packs", {
            parent: wizard.parent || "skills",
            name,
            clone_pdf: true,
          });
          wizard.path = created.display_path || created.path;
        }
        wizard.step = 4;
        render();
      } catch (e) { err.innerHTML = showError(e); }
    };
    app.appendChild(card);
    return;
  }
  const card = $(`<div class="card">
    <h2>Optional API key</h2>
    <p class="muted">Leave blank. Run check uses the built-in checker and does not need a key. Run live uses a key if you add one.</p>
    <label>OPENAI_API_KEY</label><input id="k-openai" type="password" autocomplete="off">
    <label>CURSOR_API_KEY</label><input id="k-cursor" type="password" autocomplete="off">
    <label>CODEX_API_KEY</label><input id="k-codex" type="password" autocomplete="off">
    <label>ANTHROPIC_API_KEY</label><input id="k-ant" type="password" autocomplete="off">
    <label>AI_GATEWAY_API_KEY</label><input id="k-gw" type="password" autocomplete="off">
    <p><button type="button" class="secondary" id="back">Back</button>
    <button type="button" id="skip">Skip — continue without a key</button>
    <button type="button" id="save">Save key and open pack</button></p>
  </div>`);
  card.querySelector("#back").onclick = () => { wizard.step = 3; render(); };
  const go = () => { location.hash = packHref(wizard.path); };
  card.querySelector("#skip").onclick = go;
  card.querySelector("#save").onclick = async () => {
    const body = {
      OPENAI_API_KEY: card.querySelector("#k-openai").value,
      CURSOR_API_KEY: card.querySelector("#k-cursor").value,
      CODEX_API_KEY: card.querySelector("#k-codex").value,
      ANTHROPIC_API_KEY: card.querySelector("#k-ant").value,
      AI_GATEWAY_API_KEY: card.querySelector("#k-gw").value,
    };
    try { await api("PUT", "/api/env", body); go(); }
    catch (e) { err.innerHTML = showError(e); }
  };
  app.appendChild(card);
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
    <div id="run-err"></div>
    <div id="results"></div>
  </section>`);
  head.querySelector("#run").onclick = () => startCheck(path, false);
  head.querySelector("#live").onclick = () => startCheck(path, true);
  app.appendChild(head);
  if (params.get("run") === "1") startCheck(path, false);
}

async function startCheck(path, live) {
  const box = document.getElementById("results");
  const err = document.getElementById("run-err");
  err.innerHTML = "";
  box.innerHTML = "<p class='muted'>Running check…</p>";
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
      box.innerHTML = `<p class="muted">Running ${esc(prog.current_task_id || "…")} (${prog.completed_count || 0}/${prog.task_count || "?"})</p>`;
      await new Promise((r) => setTimeout(r, 400));
      continue;
    }
    paintResult(snap, path);
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
    return `<tr><td class="${cls}">${mark}</td><td><code>${esc(t.id)}</code>${extra}</td><td>${esc(why)}</td></tr>`;
  }).join("");
  const advice = report.advice;
  let adviceHtml = "";
  if (advice && gate === "red") {
    adviceHtml = `<div class="card">
      <h2>${esc(advice.headline || "Fix")}</h2>
      <p>${esc(advice.why || "")}</p>
      <p>${esc(advice.change || "")}</p>
      ${advice.demo_note ? `<p class="muted">${esc(advice.demo_note)}</p>` : ""}
      <p>Corrected SKILL.md description (not the current one):</p>
      <pre id="paste">${esc(advice.paste || advice.description || "")}</pre>
      <button type="button" id="apply">Apply description fix on this pack</button>
      <p class="muted">CI still uses <code>skillgate check</code>.</p>
    </div>`;
  }
  box.innerHTML = `
    <p><span class="gate ${esc(gate)}">${esc(gate.toUpperCase())}</span>
      · ${esc(report.passed_count ?? 0)}/${esc(report.task_count ?? tasks.length)} tasks
      · exit ${esc(snap.exit_code)}</p>
    <p class="muted">${esc(checkerLabel(report, snap))}</p>
    <table><thead><tr><th>Result</th><th>Task</th><th>What happened</th></tr></thead><tbody>${rows}</tbody></table>
    ${adviceHtml}
  `;
  const apply = document.getElementById("apply");
  if (apply && advice) {
    apply.onclick = async () => {
      if (path.includes("skills/pdf-sabotaged") && !confirm("This edits the seed pack in your checkout. Continue?")) return;
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

window.addEventListener("hashchange", () => { wizard.step = 1; render(); });
boot().catch((e) => { app.innerHTML = showError(e); });
