// AI Trend Radar — Frontend v2
const srcIcon = { GitHub: '🐙', ProductHunt: '🟠' };
const srcCls = { GitHub: 'src-gh', ProductHunt: 'src-ph' };

let allItems = [];

async function init() {
  const resp = await fetch('data/feed.json');
  allItems = await resp.json();
  if (!allItems.length) {
    document.getElementById('list').innerHTML = '<div class="empty">No data yet.</div>';
    return;
  }
  document.getElementById('updated').textContent = 'Updated: ' + new Date().toLocaleString('zh-CN');
  renderStats();
  renderChart(allItems);
  renderList(allItems);
}

function renderStats() {
  const gh = allItems.filter(i => i.source === 'GitHub').length;
  const ph = allItems.filter(i => i.source === 'ProductHunt').length;
  document.getElementById('stat-total').textContent = allItems.length;
  document.getElementById('stat-gh').textContent = gh;
  document.getElementById('stat-ph').textContent = ph;
}

function renderChart(items) {
  const top = [...items].sort((a, b) => b.score - a.score).slice(0, 10);
  const stars = top.map(i => i.stars);
  const fmt = v => v > 999 ? (v/1000).toFixed(1) + 'k' : v;
  // Properly destroy existing chart
  const existing = Chart.getChart('chart');
  if (existing) existing.destroy();
  const ctx = document.getElementById('chart').getContext('2d');
  Chart.defaults.font = { family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", size: 12 };
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map(i => (i.title||'').split('/').pop().slice(0, 14)),
      datasets: [{
        label: 'Score',
        data: top.map(i => i.score),
        backgroundColor: top.map(i => i.source === 'GitHub' ? '#58a6ff' : '#da552f'),
        borderRadius: 6,
        maxBarThickness: 48,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { afterLabel: ctx => 'Stars: ' + fmt(stars[ctx.dataIndex]) } }
      },
      scales: {
        y: { min: 0, max: 10, ticks: { stepSize: 1, callback: v => v }, grid: { color: '#21262d' } },
        x: { grid: { display: false } }
      }
    }
  });
}

function renderList(items) {
  const catColors = {
    AI: '#8b5cf6', 'Developer-Tools': '#3b82f6', Productivity: '#10b981',
    Design: '#f59e0b', Learning: '#06b6d4', SaaS: '#ec4899', DevOps: '#f97316', Other: '#6b7280'
  };
  document.getElementById('list').innerHTML = items.map(it => {
    const icon = srcIcon[it.source] || '';
    const cls = srcCls[it.source] || '';
    const stars = it.stars > 999 ? (it.stars/1000).toFixed(1) + 'k' : it.stars;
    const g = it.growth || 0;
    const gHtml = g !== 0 ? ' <span class="' + (g>0?'growth-up':'') + '">' + (g>0?'+'+g:g) + '</span>' : '';
    const catColor = catColors[it.category] || '#6b7280';
    return '<a href="' + it.url + '" target="_blank" class="card">' +
      '<div class="card-top">' +
        '<span class="card-title">' + it.title + '</span>' +
        '<span class="src-badge ' + cls + '">' + icon + ' ' + it.source + '</span>' +
      '</div>' +
      '<div class="card-summary">' + (it.summary || '') + '</div>' +
      '<div class="card-meta">' +
        '<span>' + stars + ' stars' + gHtml + '</span>' +
        '<span class="score">Score ' + (it.score||0) + '</span>' +
        '<span class="tag" style="background:' + catColor + '20;color:' + catColor + ';border-color:' + catColor + '">' + (it.category||'Other') + '</span>' +
      '</div>' +
      (it.reason ? '<div class="card-meta" style="margin-top:6px">' + it.reason + '</div>' : '') +
    '</a>';
  }).join('');
}

function filter(src) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  const filtered = src === 'all' ? allItems : allItems.filter(i => i.source === src);
  renderChart(filtered);
  renderList(filtered);
}

document.addEventListener('DOMContentLoaded', function() {
  init();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
});
