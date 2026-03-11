<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EthicPrint — Admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #111118;
    --border: rgba(255,255,255,0.06);
    --text: #e8e8f0;
    --muted: rgba(255,255,255,0.3);
    --accent: #63cab7;
    --green: #4ade80;
    --red: #f87171;
    --yellow: #facc15;
    --orange: #fb923c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; min-height: 100vh; }
  ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }

  header {
    position: sticky; top: 0; z-index: 100;
    background: rgba(10,10,15,0.95); backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 0 32px;
    display: flex; align-items: center; gap: 24px; height: 56px;
  }
  header h1 { font-size: 13px; font-family: 'DM Mono', monospace; color: var(--accent); letter-spacing: 2px; text-transform: uppercase; }
  .tabs { display: flex; gap: 4px; margin-left: auto; }
  .tab { padding: 6px 14px; border-radius: 8px; border: 1px solid transparent; cursor: pointer; font-size: 12px; font-family: 'DM Sans', sans-serif; transition: all 0.15s; color: var(--muted); background: transparent; }
  .tab.active { background: rgba(99,202,183,0.1); border-color: rgba(99,202,183,0.25); color: var(--accent); }
  .tab:hover:not(.active) { background: rgba(255,255,255,0.04); color: var(--text); }
  .badge { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; border-radius: 99px; font-size: 10px; font-weight: 600; padding: 0 5px; margin-left: 6px; }
  .badge-pending { background: rgba(250,204,21,0.15); color: var(--yellow); }
  .badge-count { background: rgba(255,255,255,0.08); color: var(--muted); }

  .main { max-width: 900px; margin: 0 auto; padding: 32px 24px 80px; }

  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 32px; }
  .stat { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; }
  .stat-val { font-size: 28px; font-weight: 600; font-family: 'DM Mono', monospace; line-height: 1; }
  .stat-label { font-size: 11px; color: var(--muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }

  .brand-group { margin-bottom: 24px; }
  .brand-header { display: flex; align-items: center; gap: 10px; padding: 12px 0 8px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
  .brand-logo { width: 28px; height: 28px; border-radius: 7px; background: rgba(99,202,183,0.1); border: 1px solid rgba(99,202,183,0.2); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: var(--accent); flex-shrink: 0; }
  .brand-name { font-size: 14px; font-weight: 600; }
  .brand-count { font-size: 11px; color: var(--muted); }

  .proposal-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; margin-bottom: 8px; display: flex; gap: 16px; align-items: flex-start;
    transition: border-color 0.2s;
  }
  .proposal-card:hover { border-color: rgba(255,255,255,0.1); }
  .proposal-card.approved { border-color: rgba(74,222,128,0.2); background: rgba(74,222,128,0.03); }
  .proposal-card.rejected { border-color: rgba(248,113,113,0.15); background: rgba(248,113,113,0.02); opacity: 0.5; }

  .cat-badge { padding: 3px 9px; border-radius: 99px; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; flex-shrink: 0; margin-top: 2px; }
  .cat-armi { background: rgba(248,113,113,0.12); color: #f87171; }
  .cat-ambiente { background: rgba(74,222,128,0.12); color: #4ade80; }
  .cat-diritti { background: rgba(99,202,183,0.12); color: #63cab7; }
  .cat-fisco { background: rgba(250,204,21,0.12); color: #facc15; }

  .proposal-body { flex: 1; min-width: 0; }
  .proposal-title { font-size: 13px; font-weight: 500; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .proposal-publisher { font-size: 11px; color: var(--muted); margin-bottom: 6px; }
  .proposal-summary { font-size: 12px; color: rgba(255,255,255,0.45); line-height: 1.5; margin-bottom: 8px; }
  .proposal-url { font-size: 11px; font-family: 'DM Mono', monospace; color: rgba(99,202,183,0.5); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
  .proposal-url:hover { color: var(--accent); }
  .proposal-meta { font-size: 10px; color: var(--muted); margin-top: 4px; }

  .proposal-actions { display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
  .btn { padding: 7px 14px; border-radius: 8px; border: 1px solid; cursor: pointer; font-size: 12px; font-family: 'DM Sans', sans-serif; font-weight: 500; transition: all 0.15s; white-space: nowrap; }
  .btn-approve { background: rgba(74,222,128,0.1); border-color: rgba(74,222,128,0.25); color: var(--green); }
  .btn-approve:hover { background: rgba(74,222,128,0.2); }
  .btn-reject { background: rgba(248,113,113,0.07); border-color: rgba(248,113,113,0.15); color: var(--red); }
  .btn-reject:hover { background: rgba(248,113,113,0.15); }
  .btn-open { background: transparent; border-color: var(--border); color: var(--muted); font-size: 11px; padding: 5px 10px; }
  .btn-open:hover { color: var(--text); border-color: rgba(255,255,255,0.15); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .status-chip { display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px; border-radius: 99px; font-size: 11px; font-weight: 500; }
  .status-approved { background: rgba(74,222,128,0.1); color: var(--green); }
  .status-rejected { background: rgba(248,113,113,0.1); color: var(--red); }

  .empty { text-align: center; padding: 60px 20px; color: var(--muted); font-size: 14px; }
  .empty-icon { font-size: 32px; margin-bottom: 12px; }

  .loading { text-align: center; padding: 80px; color: var(--muted); font-family: 'DM Mono', monospace; font-size: 12px; letter-spacing: 2px; }

  .toast { position: fixed; bottom: 24px; right: 24px; background: #1a1a28; border: 1px solid var(--border); border-radius: 10px; padding: 12px 18px; font-size: 13px; z-index: 999; transition: opacity 0.3s; }
  .toast.hide { opacity: 0; pointer-events: none; }

  .filter-bar { display: flex; gap: 8px; margin-bottom: 20px; align-items: center; }
  .filter-bar span { font-size: 11px; color: var(--muted); margin-right: 4px; }
  .filter-chip { padding: 4px 12px; border-radius: 99px; border: 1px solid var(--border); background: transparent; color: var(--muted); font-size: 11px; cursor: pointer; font-family: 'DM Sans', sans-serif; transition: all 0.15s; }
  .filter-chip.active { background: rgba(99,202,183,0.1); border-color: rgba(99,202,183,0.25); color: var(--accent); }

  .job-badge { font-size: 9px; padding: 2px 7px; border-radius: 99px; text-transform: uppercase; letter-spacing: 0.5px; }
  .job-new { background: rgba(99,202,183,0.1); color: var(--accent); }
  .score-arrow { font-size: 18px; font-weight: 700; font-family: 'DM Mono', monospace; }
  .score-up { color: var(--green); }
  .score-down { color: var(--red); }
  .score-same { color: var(--muted); }
  .score-box { display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; padding: 8px 14px; margin-bottom: 8px; }
  .job-replacement { background: rgba(251,146,60,0.12); color: var(--orange); }
</style>
</head>
<body>

<div id="gate" style="position:fixed;inset:0;background:#0a0a0f;display:flex;align-items:center;justify-content:center;z-index:9999">
  <div style="background:#111118;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:40px;width:320px;text-align:center">
    <div style="font-family:'DM Mono',monospace;font-size:11px;color:#63cab7;letter-spacing:3px;text-transform:uppercase;margin-bottom:24px">EthicPrint Admin</div>
    <input id="pwd-input" type="password" placeholder="Password" onkeydown="if(event.key==='Enter')checkPwd()"
      style="width:100%;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:12px 16px;color:#fff;font-family:'DM Sans',sans-serif;font-size:14px;outline:none;box-sizing:border-box;margin-bottom:12px">
    <button onclick="checkPwd()" style="width:100%;background:rgba(99,202,183,0.15);border:1px solid rgba(99,202,183,0.3);color:#63cab7;padding:12px;border-radius:8px;cursor:pointer;font-family:'DM Sans',sans-serif;font-size:14px;font-weight:500">Enter</button>
    <div id="pwd-error" style="color:#f87171;font-size:12px;margin-top:10px;display:none">Wrong password</div>
  </div>
</div>

<script>
function checkPwd() {
  if (document.getElementById('pwd-input').value === 'Vigiethic93!') {
    document.getElementById('gate').style.display = 'none';
    loadAll();
  } else {
    document.getElementById('pwd-error').style.display = 'block';
    document.getElementById('pwd-input').value = '';
    document.getElementById('pwd-input').focus();
  }
}
document.addEventListener('DOMContentLoaded', () => document.getElementById('pwd-input').focus());
</script>

<header>
  <h1>EthicPrint Admin</h1>
  <div class="tabs">
    <button class="tab active" onclick="switchTab('pending')">Pending <span class="badge badge-pending" id="badge-pending">–</span></button>
    <button class="tab" onclick="switchTab('approved')">Approved <span class="badge badge-count" id="badge-approved">–</span></button>
    <button class="tab" onclick="switchTab('rejected')">Rejected <span class="badge badge-count" id="badge-rejected">–</span></button>
    <div style="width:1px;height:20px;background:rgba(255,255,255,0.08);margin:0 4px"></div>
    <button class="tab" onclick="switchTab('scores')">Score Updates <span class="badge badge-pending" id="badge-scores">–</span></button>
  </div>
</header>

<div class="main">
  <div class="stats" id="stats" style="display:none;grid-template-columns:repeat(5,1fr)">
    <div class="stat"><div class="stat-val" style="color:var(--yellow)" id="s-pending">–</div><div class="stat-label">Pending</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--green)" id="s-approved">–</div><div class="stat-label">Approved</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--red)" id="s-rejected">–</div><div class="stat-label">Rejected</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--accent)" id="s-brands">–</div><div class="stat-label">Brands</div></div>
    <div class="stat"><div class="stat-val" style="color:var(--orange)" id="s-scores">–</div><div class="stat-label">Score Updates</div></div>
  </div>

  <div class="filter-bar" id="filter-bar" style="display:none">
    <span>Category:</span>
    <button class="filter-chip active" onclick="filterCat('all')">All</button>
    <button class="filter-chip" onclick="filterCat('armi')">⚔️ Arms</button>
    <button class="filter-chip" onclick="filterCat('ambiente')">🌿 Environment</button>
    <button class="filter-chip" onclick="filterCat('diritti')">🤝 Rights</button>
    <button class="filter-chip" onclick="filterCat('fisco')">💰 Tax</button>
  </div>

  <div id="content"><div class="loading">Loading proposals...</div></div>
</div>

<div class="toast hide" id="toast"></div>

<script>
const API = "https://web-production-14708.up.railway.app";
let currentTab = "pending";
let currentCat = "all";
let allProposals = {};
let counts = { pending: 0, approved: 0, rejected: 0 };

const CAT_LABELS = { armi: "Arms", ambiente: "Environment", diritti: "Rights", fisco: "Tax" };
const CAT_ICONS = { armi: "⚔️", ambiente: "🌿", diritti: "🤝", fisco: "💰" };

function renderScoreCard(p) {
  const diff = p.proposed_score - p.current_score;
  const direction = diff > 0 ? "up" : diff < 0 ? "down" : "same";
  const arrowClass = `score-${direction}`;
  const arrow = direction === "up" ? "↑" : direction === "down" ? "↓" : "→";
  const brand = p.brands?.name || `Brand ${p.brand_id}`;
  const source = p.sources;
  const catIcons = { armi: "⚔️", ambiente: "🌿", diritti: "🤝", fisco: "💰" };

  const actions = p.status === "pending"
    ? `<div class="proposal-actions">
        <button class="btn btn-approve" onclick="approveScore(${p.id})">✓ Apply</button>
        <button class="btn btn-reject" onclick="rejectScore(${p.id})">✗ Reject</button>
       </div>`
    : `<div class="proposal-actions">
        <span class="status-chip ${p.status === 'approved' ? 'status-approved' : 'status-rejected'}">${p.status === 'approved' ? '✓ Applied' : '✗ Rejected'}</span>
       </div>`;

  return `<div class="proposal-card ${p.status}" id="score-card-${p.id}">
    <span class="cat-badge cat-${p.category_key}">${catIcons[p.category_key] || "•"} ${CAT_LABELS[p.category_key] || p.category_key}</span>
    <div class="proposal-body">
      <div class="proposal-title">${brand}</div>
      <div class="score-box">
        <span style="font-size:13px;color:var(--muted)">Current:</span>
        <span class="score-arrow" style="color:var(--text)">${p.current_score}</span>
        <span style="color:var(--muted);font-size:16px">→</span>
        <span class="score-arrow ${arrowClass}">${arrow} ${p.proposed_score}</span>
        <span style="font-size:11px;color:var(--muted);margin-left:4px">(${diff > 0 ? "+" : ""}${diff})</span>
      </div>
      ${p.motivation ? `<div class="proposal-summary">${p.motivation}</div>` : ""}
      ${source ? `<a class="proposal-url" href="${source.url}" target="_blank">↗ ${source.title || source.url}</a>` : ""}
      <div class="proposal-meta">${new Date(p.created_at).toLocaleDateString("en-GB", {day:"numeric",month:"short",year:"numeric"})}</div>
    </div>
    ${actions}
  </div>`;
}

async function approveScore(id) {
  const card = document.getElementById(`score-card-${id}`);
  card.querySelectorAll("button").forEach(b => b.disabled = true);
  try {
    await fetch(`${API}/score-proposals/${id}/approve`, { method: "POST" });
    card.classList.add("approved");
    card.querySelector(".proposal-actions").innerHTML = `<span class="status-chip status-approved">✓ Applied</span>`;
    counts.scores = (counts.scores || 0) - 1;
    document.getElementById("badge-scores").textContent = counts.scores;
    document.getElementById("s-scores").textContent = counts.scores;
    showToast("✓ Score updated in database");
  } catch(e) { showToast("✗ Error — try again", true); card.querySelectorAll("button").forEach(b => b.disabled = false); }
}

async function rejectScore(id) {
  const card = document.getElementById(`score-card-${id}`);
  card.querySelectorAll("button").forEach(b => b.disabled = true);
  try {
    await fetch(`${API}/score-proposals/${id}/reject`, { method: "POST" });
    card.classList.add("rejected");
    card.querySelector(".proposal-actions").innerHTML = `<span class="status-chip status-rejected">✗ Rejected</span>`;
    counts.scores = (counts.scores || 0) - 1;
    document.getElementById("badge-scores").textContent = counts.scores;
    document.getElementById("s-scores").textContent = counts.scores;
    showToast("Score proposal rejected");
  } catch(e) { showToast("✗ Error — try again", true); card.querySelectorAll("button").forEach(b => b.disabled = false); }
}

async function refreshScores() {
  const res = await fetch(`${API}/score-proposals?status=pending`).then(r => r.json());
  allProposals.scores = res.proposals;
  counts.scores = res.count;
  document.getElementById("badge-scores").textContent = counts.scores;
  document.getElementById("s-scores").textContent = counts.scores;
  renderTab();
}

async function loadAll() {
  const [p, a, r, s] = await Promise.all([
    fetch(`${API}/source-proposals?status=pending`).then(r => r.json()),
    fetch(`${API}/source-proposals?status=approved`).then(r => r.json()),
    fetch(`${API}/source-proposals?status=rejected`).then(r => r.json()),
    fetch(`${API}/score-proposals?status=pending`).then(r => r.json()),
  ]);
  allProposals = { pending: p.proposals, approved: a.proposals, rejected: r.proposals, scores: s.proposals };
  counts = { pending: p.count, approved: a.count, rejected: r.count, scores: s.count };

  document.getElementById("badge-pending").textContent = counts.pending;
  document.getElementById("badge-approved").textContent = counts.approved;
  document.getElementById("badge-rejected").textContent = counts.rejected;
  document.getElementById("badge-scores").textContent = counts.scores;
  document.getElementById("s-scores").textContent = counts.scores;
  document.getElementById("s-pending").textContent = counts.pending;
  document.getElementById("s-approved").textContent = counts.approved;
  document.getElementById("s-rejected").textContent = counts.rejected;

  const brands = new Set(allProposals.pending.map(p => p.brand_id));
  document.getElementById("s-brands").textContent = brands.size;
  document.getElementById("stats").style.display = "grid";
  document.getElementById("filter-bar").style.display = currentTab === "pending" ? "flex" : "none";

  renderTab();
}

function groupByBrand(proposals) {
  const groups = {};
  proposals.forEach(p => {
    const key = p.brand_id;
    if (!groups[key]) groups[key] = { name: p.brands?.name || `Brand ${key}`, proposals: [] };
    groups[key].proposals.push(p);
  });
  return groups;
}

function renderTab() {
  if (currentTab === "scores") {
    const proposals = allProposals.scores || [];
    if (proposals.length === 0) {
      document.getElementById("content").innerHTML = `<div class="empty"><div class="empty-icon">✅</div>No pending score updates<br><br><button onclick="refreshScores()" style="background:rgba(99,202,183,0.1);border:1px solid rgba(99,202,183,0.25);color:#63cab7;padding:8px 18px;border-radius:8px;cursor:pointer;font-family:'DM Sans',sans-serif;font-size:12px">↻ Refresh</button></div>`;
      return;
    }
    const groups = groupByBrand(proposals);
    let html = `<div style="text-align:right;margin-bottom:12px"><button onclick="refreshScores()" style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);color:rgba(255,255,255,0.4);padding:6px 14px;border-radius:8px;cursor:pointer;font-family:'DM Sans',sans-serif;font-size:11px">↻ Refresh</button></div>`;
    Object.values(groups).forEach(group => {
      html += `<div class="brand-group">
        <div class="brand-header">
          <div class="brand-logo">${group.name[0]}</div>
          <div class="brand-name">${group.name}</div>
          <div class="brand-count">${group.proposals.length} update${group.proposals.length !== 1 ? "s" : ""}</div>
        </div>`;
      group.proposals.forEach(p => { html += renderScoreCard(p); });
      html += `</div>`;
    });
    document.getElementById("content").innerHTML = html;
    return;
  }

  const proposals = allProposals[currentTab] || [];
  const filtered = currentCat === "all" ? proposals : proposals.filter(p => p.category_key === currentCat);
  document.getElementById("filter-bar").style.display = currentTab === "pending" ? "flex" : "none";

  if (filtered.length === 0) {
    document.getElementById("content").innerHTML = `<div class="empty"><div class="empty-icon">${currentTab === "pending" ? "✅" : "📭"}</div>No ${currentTab} proposals${currentCat !== "all" ? " in this category" : ""}</div>`;
    return;
  }

  const groups = groupByBrand(filtered);
  let html = "";
  Object.values(groups).forEach(group => {
    html += `<div class="brand-group">
      <div class="brand-header">
        <div class="brand-logo">${group.name[0]}</div>
        <div class="brand-name">${group.name}</div>
        <div class="brand-count">${group.proposals.length} proposal${group.proposals.length !== 1 ? "s" : ""}</div>
      </div>`;
    group.proposals.forEach(p => { html += renderCard(p); });
    html += `</div>`;
  });
  document.getElementById("content").innerHTML = html;
}

function renderCard(p) {
  const cat = p.category_key;
  const isApproved = p.status === "approved";
  const isRejected = p.status === "rejected";
  const jobClass = p.job_type === "replacement" ? "job-replacement" : "job-new";
  const jobLabel = p.job_type === "replacement" ? "replacement" : "new";

  const actions = currentTab === "pending"
    ? `<div class="proposal-actions">
        <button class="btn btn-approve" onclick="approve(${p.id})">✓ Approve</button>
        <button class="btn btn-reject" onclick="reject(${p.id})">✗ Reject</button>
        <button class="btn btn-open" onclick="window.open('${p.url}','_blank')">↗ Open</button>
       </div>`
    : `<div class="proposal-actions">
        <span class="status-chip ${isApproved ? "status-approved" : "status-rejected"}">${isApproved ? "✓ Approved" : "✗ Rejected"}</span>
        <button class="btn btn-open" onclick="window.open('${p.url}','_blank')" style="margin-top:6px">↗ Open</button>
       </div>`;

  return `<div class="proposal-card ${p.status}" id="card-${p.id}">
    <span class="cat-badge cat-${cat}">${CAT_ICONS[cat]} ${CAT_LABELS[cat]}</span>
    <div class="proposal-body">
      <div class="proposal-title">${p.title || p.url}</div>
      <div class="proposal-publisher">${p.publisher || "—"} <span class="job-badge ${jobClass}">${jobLabel}</span></div>
      ${p.summary ? `<div class="proposal-summary">${p.summary}</div>` : ""}
      <a class="proposal-url" href="${p.url}" target="_blank">${p.url}</a>
      <div class="proposal-meta">${new Date(p.created_at).toLocaleDateString("en-GB", {day:"numeric",month:"short",year:"numeric"})}</div>
    </div>
    ${actions}
  </div>`;
}

async function approve(id) {
  const card = document.getElementById(`card-${id}`);
  card.querySelectorAll("button").forEach(b => b.disabled = true);
  try {
    await fetch(`${API}/source-proposals/${id}/approve`, { method: "POST" });
    card.classList.add("approved");
    card.querySelector(".proposal-actions").innerHTML = `<span class="status-chip status-approved">✓ Approved</span>`;
    counts.pending--;
    document.getElementById("badge-pending").textContent = counts.pending;
    document.getElementById("s-pending").textContent = counts.pending;
    showToast("✓ Source approved and added to database");
  } catch(e) { showToast("✗ Error — try again", true); card.querySelectorAll("button").forEach(b => b.disabled = false); }
}

async function reject(id) {
  const card = document.getElementById(`card-${id}`);
  card.querySelectorAll("button").forEach(b => b.disabled = true);
  try {
    await fetch(`${API}/source-proposals/${id}/reject`, { method: "POST" });
    card.classList.add("rejected");
    card.querySelector(".proposal-actions").innerHTML = `<span class="status-chip status-rejected">✗ Rejected</span>`;
    counts.pending--;
    document.getElementById("badge-pending").textContent = counts.pending;
    document.getElementById("s-pending").textContent = counts.pending;
    showToast("Proposal rejected");
  } catch(e) { showToast("✗ Error — try again", true); card.querySelectorAll("button").forEach(b => b.disabled = false); }
}

function switchTab(tab) {
  currentTab = tab;
  currentCat = "all";
  document.querySelectorAll(".tab").forEach((t, i) => t.classList.toggle("active", ["pending","approved","rejected","scores"][i] === tab));
  document.querySelectorAll(".filter-chip").forEach(c => c.classList.toggle("active", c.textContent.trim() === "All"));
  renderTab();
}

function filterCat(cat) {
  currentCat = cat;
  document.querySelectorAll(".filter-chip").forEach(c => {
    c.classList.toggle("active", c.textContent.toLowerCase().includes(cat) || (cat === "all" && c.textContent.trim() === "All"));
  });
  renderTab();
}

function showToast(msg, error = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.borderColor = error ? "rgba(248,113,113,0.3)" : "rgba(99,202,183,0.3)";
  t.classList.remove("hide");
  setTimeout(() => t.classList.add("hide"), 3000);
}

// loadAll() called after password check
</script>
</body>
</html>
