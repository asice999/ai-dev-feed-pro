const DATA_URL = "data/feed.json";
let chart = null;
let allData = [];
let filter = "all";

const categoryTags = {
  "AI/ML": "tag-ai",
  "Developer Tools": "tag-tools",
  Infrastructure: "tag-infra",
  Frontend: "tag-front",
  Backend: "tag-back",
  "Data Science": "tag-data",
  Security: "tag-sec",
  Mobile: "tag-mob",
  DevOps: "tag-devops",
  Learning: "tag-learn",
  Other: "tag-other",
};

async function loadData() {
  try {
    const resp = await fetch(DATA_URL);
    allData = await resp.json();
    document.getElementById(
      "timeBadge"
    ).textContent = `${allData.length} repos`;
    buildFilters();
    renderChart();
    renderFeed();
  } catch (e) {
    document.getElementById("feed").innerHTML =
      '<p style="text-align:center;color:var(--muted);margin-top:40px">⏳ 数据加载失败，请稍后刷新</p>';
    console.error(e);
  }
}

function buildFilters() {
  const cats = [...new Set(allData.map((i) => i.category))].filter(Boolean);
  const bar = document.getElementById("filterBar");
  bar.innerHTML = `<span class="chip active" data-cat="all">全部</span>`;
  cats.forEach((c) => {
    bar.innerHTML += `<span class="chip" data-cat="${c}">${c}</span>`;
  });
  bar.querySelectorAll(".chip").forEach((el) => {
    el.addEventListener("click", () => {
      bar
        .querySelectorAll(".chip")
        .forEach((x) => x.classList.remove("active"));
      el.classList.add("active");
      filter = el.dataset.cat;
      renderFeed();
    });
  });
}

function scoreClass(s) {
  if (s >= 8) return "score-high";
  if (s >= 6) return "score-mid";
  return "score-low";
}

function growthClass(g) {
  if (g >= 200) return "growth-up";
  if (g > 0) return "growth-flat";
  return "growth-down";
}

function renderFeed() {
  const container = document.getElementById("feed");
  let items = filter === "all" ? allData : allData.filter((i) => i.category === filter);

  if (items.length === 0) {
    container.innerHTML =
      '<p style="text-align:center;color:var(--muted);margin-top:20px">暂无数据</p>';
    return;
  }

  container.innerHTML = items
    .map(
      (i) => `
    <div class="card">
      <div class="card-header">
        <div class="card-title">
          <a href="${i.url}" target="_blank">${i.title}</a>
        </div>
        <span class="score">
          <span class="score-dot ${scoreClass(i.score)}"></span>
          ${i.score}
        </span>
      </div>
      <div class="card-meta">
        <span class="growth ${growthClass(i.growth)}">⭐${i.stars} ${i.growth > 0 ? "+" + i.growth : ""}</span>
        <span>🍴 ${i.forks}</span>
        <span>🔧 ${i.language}</span>
        <span class="tag ${categoryTags[i.category] || "tag-other"}">${i.category}</span>
      </div>
      <div class="summary">${i.summary}</div>
    </div>`
    )
    .join("");
}

function renderChart() {
  const ctx = document.getElementById("growthChart").getContext("2d");
  if (chart) chart.destroy();

  // top 10 by growth
  const top10 = [...allData].sort((a, b) => b.growth - a.growth).slice(0, 10);
  const labels = top10.map((i) => i.title.split("/").pop());
  const growths = top10.map((i) => i.growth);
  const colors = top10.map((i) => {
    if (i.growth >= 500) return "#3fb950";
    if (i.growth >= 200) return "#58a6ff";
    return "#8b949e";
  });

  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "24h Star Growth",
          data: growths,
          backgroundColor: colors,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `+${ctx.raw} ⭐`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#21262d" },
          ticks: { color: "#8b949e", callback: (v) => "+" + v },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#e6edf3", font: { size: 12 } },
        },
      },
    },
  });
}

document.addEventListener("DOMContentLoaded", loadData);
