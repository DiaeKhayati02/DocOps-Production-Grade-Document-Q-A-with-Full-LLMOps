const API_BASE_URL = "http://localhost:8000"; // change for production deploys
const REFRESH_INTERVAL_MS = 60000;

let scoresChart = null;
let queriesChart = null;

function formatScore(value) {
  return value != null ? `${Math.round(value * 100)}%` : "—";
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function summarizeConfig(config) {
  return Object.entries(config || {})
    .map(([key, value]) => `${key}=${value}`)
    .join(", ");
}

async function loadSummary() {
  const data = await fetch(`${API_BASE_URL}/monitoring/summary`).then((r) => r.json());

  document.getElementById("metric-faithfulness").textContent = formatScore(data.avg_faithfulness_7d);
  document.getElementById("metric-answer-relevance").textContent = formatScore(
    data.avg_answer_relevance_7d
  );
  document.getElementById("metric-context-relevance").textContent = formatScore(
    data.avg_context_relevance_7d
  );
  document.getElementById("metric-latency").textContent =
    data.avg_latency_ms_7d != null ? `${Math.round(data.avg_latency_ms_7d)}ms` : "—";
}

async function loadTimeseries() {
  const data = await fetch(`${API_BASE_URL}/monitoring/timeseries`).then((r) => r.json());
  const labels = data.map((d) => d.date.slice(5)); // MM-DD

  renderScoresChart(labels, data);
  renderQueriesChart(labels, data);
}

function renderScoresChart(labels, data) {
  const datasets = [
    {
      label: "Faithfulness",
      data: data.map((d) => d.avg_faithfulness),
      borderColor: "#4f46e5",
      tension: 0.3,
    },
    {
      label: "Answer relevance",
      data: data.map((d) => d.avg_answer_relevance),
      borderColor: "#16a34a",
      tension: 0.3,
    },
    {
      label: "Context relevance",
      data: data.map((d) => d.avg_context_relevance),
      borderColor: "#d97706",
      tension: 0.3,
    },
  ];

  if (scoresChart) {
    scoresChart.data.labels = labels;
    scoresChart.data.datasets = datasets;
    scoresChart.update();
    return;
  }

  scoresChart = new Chart(document.getElementById("scores-chart"), {
    type: "line",
    data: { labels, datasets },
    options: { scales: { y: { min: 0, max: 1 } } },
  });
}

function renderQueriesChart(labels, data) {
  const dataset = {
    label: "Queries",
    data: data.map((d) => d.query_count),
    backgroundColor: "#4f46e5",
  };

  if (queriesChart) {
    queriesChart.data.labels = labels;
    queriesChart.data.datasets = [dataset];
    queriesChart.update();
    return;
  }

  queriesChart = new Chart(document.getElementById("queries-chart"), {
    type: "bar",
    data: { labels, datasets: [dataset] },
    options: { scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
}

async function loadExperiments() {
  const data = await fetch(`${API_BASE_URL}/experiments`).then((r) => r.json());
  const tbody = document.getElementById("experiments-body");

  if (data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">No experiments yet</td></tr>';
    return;
  }

  tbody.innerHTML = data
    .map(
      (exp) => `
        <tr>
          <td>${escapeHtml(exp.name)}</td>
          <td>${escapeHtml(summarizeConfig(exp.config))}</td>
          <td>${formatScore(exp.avg_faithfulness)}</td>
          <td>${formatScore(exp.avg_answer_relevance)}</td>
          <td>${formatScore(exp.avg_context_relevance)}</td>
          <td>${formatDate(exp.created_at)}</td>
        </tr>
      `
    )
    .join("");
}

async function loadCiRuns() {
  const data = await fetch(`${API_BASE_URL}/ci/runs`).then((r) => r.json());
  const tbody = document.getElementById("ci-runs-body");

  if (data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No CI runs yet</td></tr>';
    return;
  }

  tbody.innerHTML = data
    .map(
      (run) => `
        <tr>
          <td>${escapeHtml((run.commit_sha || "").slice(0, 8))}</td>
          <td>${escapeHtml(run.branch)}</td>
          <td>${formatScore(run.avg_faithfulness)}</td>
          <td>${formatScore(run.avg_answer_relevance)}</td>
          <td>${formatScore(run.avg_context_relevance)}</td>
          <td><span class="status-pill ${run.passed ? "pass" : "fail"}">${run.passed ? "PASS" : "FAIL"}</span></td>
          <td>${formatDate(run.created_at)}</td>
        </tr>
      `
    )
    .join("");
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadTimeseries(), loadExperiments(), loadCiRuns()]);
}

refreshAll();
setInterval(refreshAll, REFRESH_INTERVAL_MS);
