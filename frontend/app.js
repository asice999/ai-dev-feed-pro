// AI Trend Radar — Frontend
const srcIcon = { GitHub: '🐙', ProductHunt: '🟠' };
const srcCls = { GitHub: 'gh', ProductHunt: 'ph' };

async function init() {
  const resp = await fetch('data/feed.json');
  const items = await resp.json();
  if (!items.length) { document.getElementById('list').innerHTML = '<div class="empty">No data yet. Wait for first crawl.</div>'; return; }
  renderStats(items);
  renderChart(items);
  renderList(items);
}

function renderStats(items) {
  const gh = items.filter(i => i.source === 'GitHub').length;
  const ph = items.filter(i => i.source === 'ProductHunt').length;
  document.getElementById('stats').innerHTML = `<div class="stat"><span class="num">${items.length}</span><span class="label">Projects</span></div><div class="stat gh"><span class="num">${gh}</span><span class="label">🐙 GitHub</span></div><div class="stat ph"><span class="num">${ph}</span><span class="label">🟠 ProductHunt</span></div>`;
}

function renderChart(items) {
  const top = [...items].sort((a, b) => b.stars - a.stars).slice(0, 10);
  new Chart(document.getElementById('chart'), {
    type: 'bar',
    data: { labels: top.map(i => i.title.split('/').pop().slice(0, 14)), datasets: [{ label: 'Stars', data: top.map(i => i.stars), backgroundColor: top.map(i => i.source === 'GitHub' ? '#58a6ff' : '#ff6b35'), borderRadius: 6 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: v => v > 999 ? (v/1000).toFixed(1) + 'k' : v } } } }
  });
  document.getElementById('chart-container').style.display = 'block';
}

function renderList(items) {
  document.getElementById('list').innerHTML = items.map((it, i) => {
    const srcIcon_ = srcIcon[it.source] || '📌';
    const starStr = it.stars > 999 ? (it.stars/1000).toFixed(1) + 'k' : it.stars;
    const growth = it.growth || 0;
    const growthHTML = growth !== 0 ? `<span class="growth ${growth>0?'up':'down'}">${growth>0?'+'+growth:growth}</span>` : '';
    const catColors = {
      AI: '#8b5cf6', 'Developer-Tools': '#3b82f6', Productivity: '#10b981',
      Design: '#f59e0b', Learning: '#06b6d4', SaaS: '#ec4899', DevOps: '#f97316', Other: '#6b7280'
    };
    return `<a href="${it.url}" target="_blank" class="card ${srcCls[it.source]||''}">
      <div class="card-header">
        <span class="source-badge ${srcCls[it.source]||''}">${srcIcon_} ${it.source}</span>
        <span class="score">⭐ ${it.score}</span>
      </div>
      <h3>${it.title}</h3>
      <p class="summary">${it.summary || ''}</p>
      <div class="meta">
        <span class="stars">${starStr} stars ${growthHTML}</span>
        <span class="category" style="background:${catColors[it.category]||'#6b7280'}">${it.category||'Other'}</span>
      </div>
      ${it.reason ? `<p class="reason">💡 ${it.reason}</p>` : ''}
    </a>`;
  }).join('');
}

document.addEventListener('DOMContentLoaded', () => { init(); if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js'); });
