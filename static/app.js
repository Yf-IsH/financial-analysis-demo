const state = {
  selected: null,
  peer: null,
  period: "annual",
  analysis: null,
  tab: "income",
  metricFilter: "all",
};

const $ = (id) => document.getElementById(id);

const statusEl = $("status");
const searchInput = $("companySearch");
const peerInput = $("peerSearch");
const searchResults = $("searchResults");
const peerResults = $("peerResults");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function formatNumber(value, unit = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (unit === "%" || unit === "x" || unit === "天") {
    const scaled = unit === "%" ? value * 100 : value;
    return `${scaled.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${unit}`;
  }
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 万亿`;
  if (abs >= 1e8) return `${(value / 1e8).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 亿`;
  if (abs >= 1e4) return `${(value / 1e4).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} 万`;
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function debounce(fn, delay = 260) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

async function api(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || "请求失败");
  return payload;
}

async function doSearch(query, targetEl, onPick) {
  if (!query.trim()) {
    targetEl.style.display = "none";
    return;
  }
  const payload = await api(`/api/search?q=${encodeURIComponent(query)}`);
  targetEl.innerHTML = "";
  payload.results.forEach((company) => {
    const button = document.createElement("button");
    button.className = "result-item";
    button.innerHTML = `<span><strong>${company.ticker}</strong> ${company.title}</span><span class="muted">CIK ${company.cik}</span>`;
    button.addEventListener("click", () => {
      onPick(company);
      targetEl.style.display = "none";
    });
    targetEl.appendChild(button);
  });
  targetEl.style.display = payload.results.length ? "block" : "none";
}

function renderTable(container, rows, periods, unitByRow = () => "") {
  if (!rows || !rows.length) {
    container.className = "table-wrap empty";
    container.textContent = "没有可展示的数据";
    return;
  }
  container.className = "table-wrap";
  const head = periods.map((period) => `<th>${period}</th>`).join("");
  const body = rows
    .map((row) => {
      const unit = unitByRow(row);
      const cells = row.values
        .map((value) => `<td class="num ${value < 0 ? "negative" : ""}">${formatNumber(value, unit)}</td>`)
        .join("");
      return `<tr><td>${row.label}</td>${cells}</tr>`;
    })
    .join("");
  container.innerHTML = `<table><thead><tr><th>项目</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function metricInfo(row) {
  const details = [
    row.formula ? `<div><strong>公式：</strong>${row.formula}</div>` : "",
    row.meaning ? `<div><strong>内涵：</strong>${row.meaning}</div>` : "",
    row.note ? `<div><strong>说明：</strong>${row.note}</div>` : "",
  ]
    .filter(Boolean)
    .join("");
  return `<details class="metric-info">
    <summary>${row.label}</summary>
    <div class="metric-detail">${details || "暂无说明"}</div>
  </details>`;
}

function renderSummary() {
  const summary = $("summary");
  const data = state.analysis;
  if (!data) {
    summary.innerHTML = "";
    return;
  }
  const period = data.periods[data.periods.length - 1];
  const getRowValue = (statement, metric) => {
    const row = data.statements[statement].find((item) => item.metric === metric);
    return row ? row.values[row.values.length - 1] : null;
  };
  const netMargin = data.ratios.find((row) => row.metric === "net_margin");
  const cards = [
    ["最新期间", period],
    ["营业收入", formatNumber(getRowValue("income", "revenue"))],
    ["净利润", formatNumber(getRowValue("income", "net_income"))],
    ["销售净利率", formatNumber(netMargin?.values.at(-1), "%")],
  ];
  summary.innerHTML = cards
    .map(([label, value]) => `<div class="metric-card"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
}

function renderStatement() {
  if (!state.analysis) return;
  renderTable($("statementTable"), state.analysis.statements[state.tab], state.analysis.periods);
}

function renderRatios() {
  if (!state.analysis) return;
  const container = $("ratioTable");
  const rows = state.analysis.ratios.filter((row) => state.metricFilter === "all" || row.group === state.metricFilter);
  if (!rows.length) {
    container.className = "table-wrap empty";
    container.textContent = "没有可展示的指标";
    return;
  }
  container.className = "table-wrap";
  const head = state.analysis.periods.map((period) => `<th>${period}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = row.values
        .map((value) => `<td class="num ${value < 0 ? "negative" : ""}">${formatNumber(value, row.unit)}</td>`)
        .join("");
      return `<tr><td>${metricInfo(row)}</td><td class="group-cell">${row.group || "-"}</td>${cells}</tr>`;
    })
    .join("");
  container.innerHTML = `<table class="metrics-table"><thead><tr><th>指标</th><th>分组</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderMetricFilters() {
  const select = $("metricFilter");
  const groups = [...new Set(state.analysis.ratios.map((row) => row.group).filter(Boolean))];
  select.innerHTML = `<option value="all">全部指标</option>${groups
    .map((group) => `<option value="${group}">${group}</option>`)
    .join("")}`;
  if (!groups.includes(state.metricFilter)) state.metricFilter = "all";
  select.value = state.metricFilter;
}

function renderDupont() {
  const container = $("dupontPanel");
  if (!state.analysis?.dupont) {
    container.className = "dupont-wrap empty";
    container.textContent = "等待加载杜邦拆解";
    return;
  }
  const dupont = state.analysis.dupont;
  const lastIndex = dupont.periods.length - 1;
  const get = (metric) => dupont.rows.find((row) => row.metric === metric);
  const components = [
    get("net_margin"),
    get("asset_turnover"),
    get("equity_multiplier"),
  ];
  const dupontRoe = get("dupont_roe");
  const actualRoe = get("roe");
  container.className = "dupont-wrap";
  container.innerHTML = `
    <div class="dupont-formula">${dupont.formula}</div>
    <div class="dupont-flow">
      ${components
        .map(
          (row, index) => `<div class="dupont-box">
            <span>${row.label}</span>
            <strong>${formatNumber(row.values[lastIndex], row.unit)}</strong>
          </div>${index < components.length - 1 ? '<div class="dupont-op">×</div>' : ""}`,
        )
        .join("")}
      <div class="dupont-op">=</div>
      <div class="dupont-box result">
        <span>杜邦拆解 ROE</span>
        <strong>${formatNumber(dupontRoe.values[lastIndex], dupontRoe.unit)}</strong>
      </div>
    </div>
    <div class="dupont-foot">
      <span>最新期间：${dupont.periods[lastIndex]}</span>
      <span>实际 ROE：${formatNumber(actualRoe.values[lastIndex], actualRoe.unit)}</span>
    </div>
  `;
}

function renderTrendOptions() {
  const select = $("trendSelect");
  select.innerHTML = "";
  Object.entries(state.analysis.trends).forEach(([key, trend]) => {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = trend.label;
    select.appendChild(option);
  });
}

function drawTrend() {
  const canvas = $("trendCanvas");
  const ctx = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  if (!state.analysis) {
    ctx.fillStyle = "#66747d";
    ctx.fillText("等待加载趋势数据", 24, 40);
    return;
  }

  const key = $("trendSelect").value || Object.keys(state.analysis.trends)[0];
  const trend = state.analysis.trends[key];
  const values = trend.values;
  const valid = values.filter((value) => value !== null && value !== undefined);
  const pad = { left: 78, right: 24, top: 28, bottom: 54 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  ctx.strokeStyle = "#d9e0e3";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i <= 4; i += 1) {
    const y = pad.top + (chartH / 4) * i;
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
  }
  ctx.stroke();

  if (!valid.length) {
    ctx.fillStyle = "#66747d";
    ctx.fillText("该项目没有可用趋势数据", pad.left, pad.top + 22);
    return;
  }

  let min = Math.min(...valid);
  let max = Math.max(...valid);
  if (min === max) {
    min -= Math.abs(min || 1) * 0.2;
    max += Math.abs(max || 1) * 0.2;
  }
  const yFor = (value) => pad.top + chartH - ((value - min) / (max - min)) * chartH;
  const xFor = (index) => pad.left + (chartW / Math.max(values.length - 1, 1)) * index;

  ctx.fillStyle = "#66747d";
  ctx.font = "12px Segoe UI, Microsoft YaHei, sans-serif";
  for (let i = 0; i <= 4; i += 1) {
    const value = max - ((max - min) / 4) * i;
    ctx.fillText(formatNumber(value), 8, pad.top + (chartH / 4) * i + 4);
  }

  ctx.strokeStyle = "#0b6b78";
  ctx.lineWidth = 3;
  ctx.beginPath();
  values.forEach((value, index) => {
    if (value === null || value === undefined) return;
    const x = xFor(index);
    const y = yFor(value);
    if (index === 0 || values[index - 1] === null || values[index - 1] === undefined) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  values.forEach((value, index) => {
    const x = xFor(index);
    ctx.fillStyle = "#66747d";
    ctx.save();
    ctx.translate(x, height - 18);
    ctx.rotate(-Math.PI / 5);
    ctx.fillText(state.analysis.periods[index], -18, 0);
    ctx.restore();
    if (value === null || value === undefined) return;
    ctx.fillStyle = "#0b6b78";
    ctx.beginPath();
    ctx.arc(x, yFor(value), 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

async function loadAnalysis() {
  if (!state.selected) {
    setStatus("请先选择主公司。", true);
    return;
  }
  setStatus(`正在读取 ${state.selected.ticker} 的真实 SEC 财报数据...`);
  try {
    state.analysis = await api(`/api/analysis?cik=${state.selected.cik}&period=${state.period}`);
    setStatus(`${state.analysis.company.ticker} ${state.analysis.company.title}：已加载 ${state.analysis.periods.length} 个期间。`);
    renderSummary();
    renderStatement();
    renderMetricFilters();
    renderRatios();
    renderDupont();
    renderTrendOptions();
    drawTrend();
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadCompare() {
  if (!state.selected || !state.peer) {
    setStatus("请先选择主公司和可比公司。", true);
    return;
  }
  setStatus(`正在对比 ${state.selected.ticker} 与 ${state.peer.ticker} 的专业指标...`);
  try {
    const payload = await api(`/api/compare?a=${state.selected.cik}&b=${state.peer.cik}&period=${state.period}`);
    $("compareMeta").textContent = `${payload.left.ticker} ${payload.leftLatestPeriod} vs ${payload.right.ticker} ${payload.rightLatestPeriod}`;
    const rows = payload.rows
      .map((row) => {
        const unit = row.unit || "";
        return `<tr>
          <td>${metricInfo(row)}</td>
          <td class="group-cell">${row.group || "-"}</td>
          <td class="num">${formatNumber(row.left, unit)}</td>
          <td class="num">${formatNumber(row.right, unit)}</td>
          <td class="num ${row.spread < 0 ? "negative" : "positive"}">${formatNumber(row.spread, unit)}</td>
        </tr>`;
      })
      .join("");
    $("compareTable").className = "table-wrap";
    $("compareTable").innerHTML = `<table class="metrics-table"><thead><tr><th>指标</th><th>分组</th><th>${payload.left.ticker}</th><th>${payload.right.ticker}</th><th>差值</th></tr></thead><tbody>${rows}</tbody></table>`;
    setStatus("可比公司专业指标对比已完成。");
  } catch (error) {
    setStatus(error.message, true);
  }
}

searchInput.addEventListener(
  "input",
  debounce(() => doSearch(searchInput.value, searchResults, (company) => {
    state.selected = company;
    searchInput.value = `${company.ticker} - ${company.title}`;
  })),
);

peerInput.addEventListener(
  "input",
  debounce(() => doSearch(peerInput.value, peerResults, (company) => {
    state.peer = company;
    peerInput.value = `${company.ticker} - ${company.title}`;
  })),
);

$("loadBtn").addEventListener("click", loadAnalysis);
$("compareBtn").addEventListener("click", loadCompare);
$("trendSelect").addEventListener("change", drawTrend);
$("metricFilter").addEventListener("change", () => {
  state.metricFilter = $("metricFilter").value;
  renderRatios();
});
window.addEventListener("resize", drawTrend);

document.querySelectorAll(".segmented button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segmented button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.period = button.dataset.period;
    if (state.selected) loadAnalysis();
  });
});

document.querySelectorAll(".tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.tab = button.dataset.tab;
    renderStatement();
  });
});

drawTrend();
