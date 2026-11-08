"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  connected: false,
  targets: [],
  position: null,
  images: [],
  selected: null, // 선택된 이미지 메타데이터
  logSeq: 0,
  jobStatus: "idle",
  jobResultsKey: "",
};

// ---------------- 공통 ----------------
async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(", ");
    throw new Error(msg || `요청 실패 (${res.status})`);
  }
  return data;
}

let toastTimer;
function toast(msg, isErr = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 3200);
}

async function run(btn, fn) {
  if (btn) btn.disabled = true;
  try { return await fn(); }
  catch (e) { toast(e.message, true); }
  finally { if (btn) btn.disabled = false; }
}

const fmt = (v, d = 1) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));
function raText(h) {
  if (h == null) return "—";
  let s = ((h % 24) + 24) % 24 * 3600;
  const hh = Math.floor(s / 3600); s -= hh * 3600;
  const mm = Math.floor(s / 60); s -= mm * 60;
  return `${String(hh).padStart(2, "0")}h ${String(mm).padStart(2, "0")}m ${s.toFixed(1).padStart(4, "0")}s`;
}
function decText(d) {
  if (d == null) return "—";
  const sign = d < 0 ? "-" : "+";
  let s = Math.round(Math.abs(d) * 3600);
  const dd = Math.floor(s / 3600); s -= dd * 3600;
  const mm = Math.floor(s / 60); s -= mm * 60;
  return `${sign}${String(dd).padStart(2, "0")}° ${String(mm).padStart(2, "0")}' ${String(s).padStart(2, "0")}"`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- 연결 ----------------
$("conn-mode").addEventListener("change", updateModeUI);
function updateModeUI() {
  const alpaca = $("conn-mode").value === "alpaca";
  document.querySelectorAll(".alpaca-only").forEach((el) => (el.style.display = alpaca ? "" : "none"));
}

$("btn-connect").onclick = (e) => run(e.target, async () => {
  const st = await api("/telescope/connect", {
    method: "POST",
    body: { mode: $("conn-mode").value, host: $("conn-host").value, port: Number($("conn-port").value) },
  });
  toast(`연결됨: ${st.telescope}`);
  await refreshStatus();
  await loadTargets();
});

$("btn-disconnect").onclick = (e) => run(e.target, async () => {
  await api("/telescope/disconnect", { method: "POST" });
  toast("연결 해제");
  await refreshStatus();
});

// ---------------- 대상 ----------------
async function loadTargets() {
  state.targets = await api("/targets");
  const opts = state.targets.map((t) => `<option value="${esc(t.name)}">${esc(t.name)}${t.separation_deg != null ? ` (${t.separation_deg.toFixed(1)}°)` : ""}</option>`).join("");
  const keepMove = $("move-target").value;
  const keepCor = $("cor-target").value;
  $("move-target").innerHTML = `<option value="">직접 입력</option>` + opts;
  $("cor-target").innerHTML = opts;
  $("move-target").value = keepMove;
  if (keepCor) $("cor-target").value = keepCor;

  const box = $("obs-targets");
  if (!box.dataset.ready) {
    box.innerHTML = state.targets.map((t, i) =>
      `<label><input type="checkbox" value="${esc(t.name)}" ${i < 3 ? "checked" : ""}> ${esc(t.name)}</label>`).join("");
    box.dataset.ready = "1";
  }
  drawSkyMap();
}

$("move-target").addEventListener("change", () => {
  const t = state.targets.find((x) => x.name === $("move-target").value);
  if (t) { $("move-ra").value = t.ra; $("move-dec").value = t.dec; }
});

// ---------------- 망원경 ----------------
$("btn-move").onclick = (e) => run(e.target, async () => {
  const target = $("move-target").value;
  const body = target ? { target } : { ra: parseFloat($("move-ra").value), dec: parseFloat($("move-dec").value) };
  if (!target && (isNaN(body.ra) || isNaN(body.dec))) throw new Error("RA/Dec 를 입력하거나 대상을 선택하세요.");
  const r = await api("/telescope/move", { method: "POST", body });
  toast(`이동 시작${r.estimated_seconds != null ? ` (약 ${r.estimated_seconds.toFixed(1)}초)` : ""}`);
});

$("btn-stop").onclick = (e) => run(e.target, async () => {
  await api("/telescope/stop", { method: "POST" });
  toast("정지");
});

// ---------------- 하늘 지도 ----------------
const sky = $("skymap");
function skyXY(raH, dec) {
  // RA는 왼쪽으로 증가 (천구를 올려다보는 방향)
  return [(1 - raH / 24) * sky.width, (0.5 - dec / 180) * sky.height];
}
function drawSkyMap() {
  const g = sky.getContext("2d");
  const W = sky.width, H = sky.height;
  g.fillStyle = "#050810"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#16213a"; g.lineWidth = 1; g.font = "10px Consolas, monospace"; g.fillStyle = "#4b5d80";
  for (let h = 0; h <= 24; h += 3) {
    const [x] = skyXY(h, 0);
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
    if (h < 24) g.fillText(`${h}h`, x - 16, H - 4);
  }
  for (let d = -60; d <= 60; d += 30) {
    const [, y] = skyXY(0, d);
    g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    g.fillText(`${d > 0 ? "+" : ""}${d}°`, 3, y - 3);
  }
  for (const t of state.targets) {
    const [x, y] = skyXY(t.ra, t.dec);
    g.fillStyle = t.type === "star" ? "#e8eefc" : "#b9a7ff";
    g.beginPath(); g.arc(x, y, t.type === "star" ? 2.5 : 3, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#7f90b3"; g.fillText(t.name.split(" ")[0], x + 5, y + 3);
  }
  const p = state.position;
  if (p && p.ra != null) {
    const [x, y] = skyXY(p.ra, p.dec);
    g.strokeStyle = p.slewing ? "#ffb648" : "#5fa8ff"; g.lineWidth = 1.5;
    g.beginPath(); g.arc(x, y, 7, 0, Math.PI * 2); g.stroke();
    g.beginPath(); g.moveTo(x - 12, y); g.lineTo(x - 4, y); g.moveTo(x + 4, y); g.lineTo(x + 12, y);
    g.moveTo(x, y - 12); g.lineTo(x, y - 4); g.moveTo(x, y + 4); g.lineTo(x, y + 12); g.stroke();
  }
}
sky.addEventListener("click", (ev) => {
  const r = sky.getBoundingClientRect();
  const x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
  const ra = Math.min(23.9999, Math.max(0, (1 - x) * 24));
  const dec = Math.min(90, Math.max(-90, (0.5 - y) * 180));
  $("move-target").value = "";
  $("move-ra").value = ra.toFixed(4);
  $("move-dec").value = dec.toFixed(4);
});

// ---------------- 카메라 / 이미지 ----------------
$("btn-capture").onclick = (e) => run(e.target, async () => {
  const meta = await api("/camera/capture", {
    method: "POST",
    body: { exposure: parseFloat($("cap-exposure").value), analyze: $("cap-analyze").checked },
  });
  toast(`촬영 완료: ${meta.id}`);
  await loadImages();
  await selectImage(meta.id);
});

$("btn-analyze").onclick = (e) => run(e.target, async () => {
  if (!state.selected) throw new Error("이미지를 먼저 선택하세요.");
  const meta = await api(`/vision/analyze/${state.selected.id}`, { method: "POST" });
  state.selected = meta;
  renderViewer();
  toast(`분석 완료: 별 ${meta.analysis.star_count}개`);
});

$("btn-track").onclick = (e) => run(e.target, async () => {
  if (!state.selected) throw new Error("이미지를 먼저 선택하세요.");
  const idx = state.images.findIndex((m) => m.id === state.selected.id);
  const prev = state.images[idx + 1];
  if (!prev) throw new Error("비교할 이전 이미지가 없습니다.");
  const r = await api("/vision/track", { method: "POST", body: { image_a: prev.id, image_b: state.selected.id } });
  toast(`이동량 dx=${r.dx}px, dy=${r.dy}px (거리 ${r.distance}px, 신뢰도 ${r.response})`);
});

async function loadImages() {
  state.images = await api("/images?limit=30");
  $("thumbs").innerHTML = state.images.map((m) => `
    <div class="thumb ${state.selected && state.selected.id === m.id ? "sel" : ""}" data-id="${esc(m.id)}" title="${esc(m.id)}">
      <img src="/images/${encodeURIComponent(m.id)}/png" loading="lazy" alt="">
      <div class="cap">${esc(m.target || m.purpose || "")} ${esc(m.id.slice(9, 15))}</div>
    </div>`).join("");
  $("thumbs").querySelectorAll(".thumb").forEach((el) => (el.onclick = () => run(null, () => selectImage(el.dataset.id))));
}

const viewerImg = new Image();
async function selectImage(id) {
  state.selected = await api(`/images/${encodeURIComponent(id)}`);
  viewerImg.onload = renderViewer;
  viewerImg.src = `/images/${encodeURIComponent(id)}/png?t=${Date.now()}`;
  $("btn-fits").href = `/images/${encodeURIComponent(id)}/fits`;
  $("thumbs").querySelectorAll(".thumb").forEach((el) => el.classList.toggle("sel", el.dataset.id === id));
}

function renderViewer() {
  const m = state.selected;
  const cv = $("viewer");
  const g = cv.getContext("2d");
  if (!m || !viewerImg.complete || !viewerImg.naturalWidth) return;
  $("viewer-empty").style.display = "none";
  cv.width = m.width; cv.height = m.height;
  g.drawImage(viewerImg, 0, 0);

  if ($("ov-cross").checked) {
    g.strokeStyle = "rgba(95,168,255,.55)"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(cv.width / 2, 0); g.lineTo(cv.width / 2, cv.height);
    g.moveTo(0, cv.height / 2); g.lineTo(cv.width, cv.height / 2); g.stroke();
  }
  if ($("ov-stars").checked && m.stars) {
    g.strokeStyle = "rgba(61,220,151,.85)"; g.lineWidth = 1.2;
    for (const s of m.stars) {
      const r = Math.min(14, 4 + Math.sqrt(s.area));
      g.beginPath(); g.arc(s.x, s.y, r, 0, Math.PI * 2); g.stroke();
    }
  }
  const solve = m.analysis && m.analysis.solve;
  if (solve && solve.success && m.target) {
    // 목표 천체의 실제 위치를 영상 위에 표시 (보고 좌표 대비 이동량 활용)
    const t = state.targets.find((x) => x.name === m.target);
    if (t) {
      const scale = (m.pixel_scale || 4.5) / 3600;
      const cosd = Math.cos(solve.dec * Math.PI / 180);
      let dra = ((t.ra - solve.ra + 12) % 24 + 24) % 24 - 12;
      const x = cv.width / 2 + dra * 15 * cosd / scale;
      const y = cv.height / 2 - (t.dec - solve.dec) / scale;
      g.strokeStyle = "#ffb648"; g.lineWidth = 1.5;
      g.strokeRect(x - 12, y - 12, 24, 24);
      g.fillStyle = "#ffb648"; g.font = "13px sans-serif"; g.fillText(t.name, x + 16, y + 4);
    }
  }
  renderAnalysis();
}
["ov-stars", "ov-cross"].forEach((id) => $(id).addEventListener("change", renderViewer));

function renderAnalysis() {
  const m = state.selected;
  if (!m) return;
  const a = m.analysis || {};
  const s = a.solve || {};
  const items = [
    ["이미지", m.id],
    ["대상 / 목적", `${m.target || "—"} / ${m.purpose || "—"}`],
    ["노출", `${m.exposure}s`],
    ["보고 좌표", `${raText(m.ra)}  ${decText(m.dec)}`],
    ["탐지된 별", a.star_count ?? "—"],
    ["Plate Solving", s.success ? `<span class="ok">성공 (${s.matched}개 일치)</span>` : (s.message ? `<span class="bad">${esc(s.message)}</span>` : "—"), true],
  ];
  if (s.success) {
    items.push(["실제 좌표", `${raText(s.ra)}  ${decText(s.dec)}`]);
    items.push(["영상 이동량", `dx ${s.shift_px.dx}px, dy ${s.shift_px.dy}px`]);
    items.push(["잔차 RMS", `${s.rms_arcsec}"`]);
    const t = state.targets.find((x) => x.name === m.target);
    if (t) items.push(["목표 오차", `${fmt(angSepArcsec(t.ra, t.dec, s.ra, s.dec))}"`]);
  }
  $("analysis").innerHTML = items.map(([k, v, raw]) =>
    `<div class="item"><div class="k">${k}</div><div class="v">${raw ? v : esc(v)}</div></div>`).join("");
}

function angSepArcsec(ra1, d1, ra2, d2) {
  const r = Math.PI / 180;
  const a1 = ra1 * 15 * r, a2 = ra2 * 15 * r, b1 = d1 * r, b2 = d2 * r;
  const s = Math.sin((b2 - b1) / 2) ** 2 + Math.cos(b1) * Math.cos(b2) * Math.sin((a2 - a1) / 2) ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(s))) / r * 3600;
}

// ---------------- 자동 보정 / 관측 ----------------
$("btn-correct").onclick = (e) => run(e.target, async () => {
  await api("/correction/run", {
    method: "POST",
    body: {
      target: $("cor-target").value,
      tolerance_arcsec: parseFloat($("cor-tol").value),
      max_iterations: parseInt($("cor-iter").value, 10),
      exposure: parseFloat($("cor-exp").value),
    },
  });
  toast("자동 보정 시작");
  refreshStatus();
});

$("btn-observe").onclick = (e) => run(e.target, async () => {
  const targets = [...$("obs-targets").querySelectorAll("input:checked")].map((i) => i.value);
  if (!targets.length) throw new Error("관측할 대상을 선택하세요.");
  await api("/observation/start", {
    method: "POST",
    body: {
      targets,
      exposure: parseFloat($("obs-exp").value),
      final_exposure: parseFloat($("obs-final").value),
      tolerance_arcsec: parseFloat($("cor-tol").value),
      max_iterations: parseInt($("cor-iter").value, 10),
    },
  });
  toast(`자동 관측 시작 (${targets.length}개 대상)`);
  refreshStatus();
});

$("btn-cancel").onclick = (e) => run(e.target, async () => {
  await api("/observation/cancel", { method: "POST" });
  toast("취소 요청");
});

const STATUS_KO = { idle: "대기", running: "실행 중", done: "완료", failed: "실패", cancelled: "취소됨" };

function renderJob(job) {
  const badge = $("job-badge");
  badge.textContent = (job.kind === "observation" ? "관측 " : job.kind === "correction" ? "보정 " : "") + (STATUS_KO[job.status] || job.status);
  badge.className = "badge " + job.status;
  $("job-bar").style.width = `${Math.round((job.progress || 0) * 100)}%`;

  let info = "실행 중인 작업 없음";
  if (job.status !== "idle") {
    info = `${job.kind === "observation" ? "자동 관측" : "자동 보정"} · ${STATUS_KO[job.status]}`;
    if (job.current_target && job.status === "running") info += ` · ${job.current_target}`;
    if (job.step) info += ` · ${job.step}`;
    if (job.error) info += ` · 오류: ${job.error}`;
  }
  $("job-info").textContent = info;

  const key = job.job_id + ":" + job.results.length;
  if (key === state.jobResultsKey) return;
  state.jobResultsKey = key;

  $("job-results").innerHTML = job.results.length ? `
    <table>
      <tr><th>대상</th><th>결과</th><th>최종 오차</th><th>반복</th><th></th></tr>
      ${job.results.map((r, i) => `
        <tr>
          <td>${esc(r.target)}</td>
          <td class="${r.success ? "ok" : "bad"}">${r.success ? "보정 성공" : "실패"}</td>
          <td>${r.final_error_arcsec != null ? r.final_error_arcsec + '"' : "—"}</td>
          <td>${r.iterations.length}</td>
          <td><a data-img="${esc(r.observation_image_id || (r.iterations.at(-1) || {}).image_id || "")}">보기</a></td>
        </tr>
        <tr><td colspan="5"><canvas class="iter-chart" data-idx="${i}" width="300" height="60"></canvas></td></tr>`).join("")}
    </table>` : "";
  $("job-results").querySelectorAll("a[data-img]").forEach((a) => (a.onclick = () => a.dataset.img && run(null, () => selectImage(a.dataset.img))));
  $("job-results").querySelectorAll("canvas.iter-chart").forEach((cv) => drawIterChart(cv, job.results[+cv.dataset.idx]));
  loadImages();
}

function drawIterChart(cv, res) {
  // 반복별 오차(arcsec)를 로그 스케일 막대로 표시
  const g = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  g.clearRect(0, 0, W, H);
  const its = res.iterations.filter((i) => i.solved);
  if (!its.length) return;
  const max = Math.log10(Math.max(...its.map((i) => i.error_arcsec), res.tolerance_arcsec) + 1);
  const bw = Math.min(50, (W - 20) / its.length - 6);
  const tolY = H - 12 - (Math.log10(res.tolerance_arcsec + 1) / max) * (H - 18);
  its.forEach((it, k) => {
    const h = (Math.log10(it.error_arcsec + 1) / max) * (H - 18);
    const x = 10 + k * (bw + 6);
    g.fillStyle = it.error_arcsec <= res.tolerance_arcsec ? "#3ddc97" : "#5fa8ff";
    g.fillRect(x, H - 12 - h, bw, h);
    g.fillStyle = "#8193b2"; g.font = "10px Consolas"; g.fillText(`${it.error_arcsec}"`, x, H - 2);
  });
  g.strokeStyle = "rgba(255,182,72,.7)"; g.setLineDash([3, 3]);
  g.beginPath(); g.moveTo(0, tolY); g.lineTo(W, tolY); g.stroke(); g.setLineDash([]);
}

// ---------------- 상태 폴링 ----------------
async function refreshStatus() {
  const st = await api("/status");
  const d = st.devices;
  state.connected = d.connected;
  $("conn-badge").textContent = d.connected ? `연결됨 · ${d.mode === "sim" ? "가상 장비" : "Alpaca"}` : "연결 안 됨";
  $("conn-badge").className = "badge " + (d.connected ? "on" : "off");
  $("device-info").innerHTML = d.connected
    ? `${esc(d.telescope)}<br>${esc(d.camera.name)} · ${d.camera.width}×${d.camera.height}px · ${d.camera.pixel_scale}"/px`
    : "";

  const p = st.position;
  state.position = p && p.connected ? p : null;
  $("pos-ra").textContent = state.position ? raText(p.ra) : "—";
  $("pos-dec").textContent = state.position ? decText(p.dec) : "—";
  $("pos-state").textContent = state.position ? (p.slewing ? "이동 중" : p.tracking ? "추적 중" : "정지") : "—";
  $("pos-state").style.color = state.position && p.slewing ? "var(--warn)" : "";

  const busy = st.job.status === "running";
  ["btn-move", "btn-capture", "btn-correct", "btn-observe", "btn-connect", "btn-disconnect"].forEach((id) => ($(id).disabled = busy));
  $("btn-cancel").disabled = !busy;
  renderJob(st.job);
  drawSkyMap();
}

async function refreshLogs() {
  const items = await api(`/logs?after=${state.logSeq}`);
  if (!items.length) return;
  const box = $("log");
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 10;
  for (const r of items) {
    const div = document.createElement("div");
    div.className = r.level;
    div.innerHTML = `<span class="t">${r.time}</span>${esc(r.message)}`;
    box.appendChild(div);
    state.logSeq = r.seq;
  }
  while (box.children.length > 400) box.removeChild(box.firstChild);
  if (atBottom) box.scrollTop = box.scrollHeight;
}
$("btn-clear-log").onclick = () => ($("log").innerHTML = "");

async function loop() {
  try { await refreshStatus(); } catch (e) { /* 서버 재시작 등 */ }
  try { await refreshLogs(); } catch (e) { }
  setTimeout(loop, 800);
}

// 대상 목록의 각거리 표시는 주기적으로 갱신
setInterval(() => { if (state.connected) loadTargets().catch(() => { }); }, 5000);

(async function init() {
  updateModeUI();
  await loadTargets().catch(() => { });
  await loadImages().catch(() => { });
  if (state.images.length) await selectImage(state.images[0].id).catch(() => { });
  loop();
})();
