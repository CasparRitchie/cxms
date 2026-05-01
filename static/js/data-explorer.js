const datasetInput = document.getElementById("datasetInput");
const analyseBtn = document.getElementById("analyseDatasetBtn");
const loadExampleBtn = document.getElementById("loadExampleBtn");
const statusEl = document.getElementById("analysisStatus");
const resultsSection = document.getElementById("resultsSection");

const summaryTab = document.getElementById("summaryTab");
const qualityTab = document.getElementById("qualityTab");
const columnsTab = document.getElementById("columnsTab");
const chartsTab = document.getElementById("chartsTab");
const relationshipsTab = document.getElementById("relationshipsTab");
const advancedTab = document.getElementById("advancedTab");
const mlTab = document.getElementById("mlTab");
const thesesTab = document.getElementById("thesesTab");

const chartguideTab = document.getElementById("chartguideTab");

const exampleCsv = `date,region,channel,nps,response_time_minutes,revenue,complaints
2026-01-01,South,Web,9,12,1200,0
2026-01-02,North,Phone,6,35,800,1
2026-01-03,South,Web,10,8,1400,0
2026-01-04,West,Email,4,60,500,3
2026-01-05,North,Phone,7,25,900,1
2026-01-06,East,Web,8,18,1100,0
2026-01-07,West,Email,3,75,450,4
2026-01-08,South,Web,9,10,1300,0
2026-01-09,East,Phone,5,50,650,2
2026-01-10,North,Web,8,20,1000,1
2026-02-01,South,Web,10,9,1500,0
2026-02-02,North,Phone,6,42,780,2
2026-02-03,East,Email,7,33,850,1
2026-02-04,West,Email,2,90,400,5
2026-02-05,South,Phone,9,15,1250,0`;

loadExampleBtn.addEventListener("click", () => {
  datasetInput.value = exampleCsv;
});

const loadIrisBtn = document.getElementById("loadIrisBtn");

loadIrisBtn.addEventListener("click", async () => {
  await loadSampleDataset("iris");
});

const loadTitanicBtn = document.getElementById("loadTitanicBtn");

loadTitanicBtn.addEventListener("click", async () => {
  await loadSampleDataset("titanic");
});

async function loadSampleDataset(datasetName) {
  setStatus(`Loading ${datasetName} dataset...`, "loading");

  try {
    const response = await fetch(`/api/data-explorer/sample/${datasetName}`);
    const result = await response.json();

    if (!response.ok || !result.ok) {
      throw new Error(result.error || `Could not load ${datasetName} dataset.`);
    }

    datasetInput.value = result.csv;
    setStatus(`${datasetName} dataset loaded. Click Analyse dataset.`, "success");
  } catch (error) {
    console.error(error);
    setStatus(error.message, "error");
  }
}

analyseBtn.addEventListener("click", async () => {
  const dataset = datasetInput.value.trim();

  if (!dataset) {
    setStatus("Please paste a CSV dataset first.", "error");
    return;
  }

  setStatus("Analysing dataset...", "loading");
  analyseBtn.disabled = true;

  try {
    const response = await fetch("/api/data-explorer/analyse", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ dataset }),
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      throw new Error(result.error || "Analysis failed.");
    }

    renderAnalysis(result.analysis);
    setStatus("Analysis complete.", "success");
    resultsSection.classList.remove("hidden");
  } catch (error) {
    console.error(error);
    setStatus(error.message, "error");
  } finally {
    analyseBtn.disabled = false;
  }
});

document.querySelectorAll(".eda-tab").forEach((button) => {
  button.addEventListener("click", () => {
    const tabName = button.dataset.tab;

    document.querySelectorAll(".eda-tab").forEach((tab) => {
      tab.classList.remove("active");
    });

    document.querySelectorAll(".eda-tab-panel").forEach((panel) => {
      panel.classList.remove("active");
    });

    button.classList.add("active");
    document.getElementById(`${tabName}Tab`).classList.add("active");
  });
});

function setStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = `analysis-status ${type}`;
}

function renderAnalysis(analysis) {
  renderSummary(analysis);
  renderQuality(analysis);
  renderColumns(analysis);
  renderCharts(analysis);
  renderChartGuide(analysis);
  renderRelationships(analysis);
  renderAdvanced(analysis);
  renderML(analysis);
  renderTheses(analysis);
}

function renderSummary(analysis) {
  const summary = analysis.summary;
  const schema = analysis.schema;

  summaryTab.innerHTML = `
    <div class="results-grid">
      ${metricCard("Rows", summary.rows)}
      ${metricCard("Columns", summary.columns)}
      ${metricCard("Numeric", summary.numeric_columns)}
      ${metricCard("Categorical", summary.categorical_columns)}
      ${metricCard("Dates", summary.datetime_columns)}
      ${metricCard("Missing cells", summary.total_missing_cells)}
    </div>

    <div class="analysis-card">
      <h3>Detected schema</h3>
      ${schemaGroup("Numeric", schema.numeric)}
      ${schemaGroup("Categorical", schema.categorical)}
      ${schemaGroup("Datetime", schema.datetime)}
      ${schemaGroup("Text", schema.text)}
      ${schemaGroup("Likely IDs", schema.likely_id)}
    </div>
  `;
}

function renderQuality(analysis) {
  const quality = analysis.quality;

  qualityTab.innerHTML = `
    <div class="results-grid">
      ${metricCard("Duplicate rows", quality.duplicate_rows)}
      ${metricCard("Missing cells", quality.total_missing_cells)}
      ${metricCard("Missing %", `${quality.missing_percent_total}%`)}
    </div>

    <div class="analysis-card">
      <h3>Missing values by column</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Column</th>
              <th>Missing</th>
              <th>Missing %</th>
            </tr>
          </thead>
          <tbody>
            ${quality.missing_by_column.map((item) => `
              <tr>
                <td>${escapeHtml(item.column)}</td>
                <td>${item.missing}</td>
                <td>${item.missing_percent}%</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderColumns(analysis) {
  columnsTab.innerHTML = `
    <div class="analysis-card">
      <h3>Column-level analysis</h3>
      <div class="column-grid">
        ${analysis.columns.map(renderColumnCard).join("")}
      </div>
    </div>
  `;
}

function renderColumnCard(column) {
  const numericStats = column.inferred_type === "numeric"
    ? `
      <p><strong>Mean:</strong> ${valueOrDash(column.mean)}</p>
      <p><strong>Median:</strong> ${valueOrDash(column.median)}</p>
      <p><strong>Min:</strong> ${valueOrDash(column.min)}</p>
      <p><strong>Max:</strong> ${valueOrDash(column.max)}</p>
      <p><strong>Std:</strong> ${valueOrDash(column.std)}</p>
    `
    : "";

  const topValues = column.top_values
    ? `
      <div class="top-values">
        <strong>Top values</strong>
        ${column.top_values.map((item) => `
          <div class="top-value-row">
            <span>${escapeHtml(item.value)}</span>
            <span>${item.count}</span>
          </div>
        `).join("")}
      </div>
    `
    : "";

  return `
    <article class="column-card">
      <h4>${escapeHtml(column.name)}</h4>
      <p><strong>Type:</strong> ${escapeHtml(column.inferred_type)}</p>
      <p><strong>Missing:</strong> ${column.missing}</p>
      <p><strong>Unique:</strong> ${column.unique}</p>
      ${numericStats}
      ${topValues}
    </article>
  `;
}

function renderCharts(analysis) {
  chartsTab.innerHTML = `
    <div class="section-heading">
      <p class="eyebrow">Visual EDA</p>
      <h2>Recommended charts</h2>
      <p>
        These are selected automatically from the detected data types, inspired by the Data-to-Viz decision framework.
      </p>
    </div>
    <div id="chartGrid" class="chart-grid"></div>
  `;

  const chartGrid = document.getElementById("chartGrid");

  analysis.charts.forEach((chart, index) => {
    const chartWrapper = document.createElement("article");
    chartWrapper.className = "chart-card";

    const chartId = `plotlyChart${index}`;

    chartWrapper.innerHTML = `
      <div class="chart-card-header">
        <div>
          <h3>${escapeHtml(chart.title)}</h3>
          <p>${escapeHtml(chart.why || "")}</p>
        </div>
        <span>${escapeHtml(chart.phase)}</span>
      </div>
      <div id="${chartId}" class="plotly-chart"></div>
    `;

    chartGrid.appendChild(chartWrapper);
    drawChart(chartId, chart);
  });
}

function renderChartGuide(analysis) {
  const schema = analysis.schema;

  const guideItems = [
    {
      family: "Numeric",
      detected: schema.numeric,
      charts: "Histogram, density, boxplot, violin, ridgeline",
      use: "Understand spread, skew, outliers and distribution shape.",
    },
    {
      family: "Categorical",
      detected: schema.categorical,
      charts: "Bar chart, lollipop chart, circular bar chart, word cloud for text-like categories",
      use: "Compare category counts and identify dominant groups.",
    },
    {
      family: "Numeric + categorical",
      detected: [...schema.numeric, ...schema.categorical],
      charts: "Grouped bar, boxplot by group, violin by group, radar for small comparable profiles",
      use: "Compare numeric measures across groups or segments.",
    },
    {
      family: "Numeric + numeric",
      detected: schema.numeric,
      charts: "Scatter, bubble, 2D density, hexbin, correlogram, heatmap",
      use: "Explore relationships, correlation, clustering and outliers.",
    },
    {
      family: "Time series",
      detected: schema.datetime,
      charts: "Line chart, area chart, stacked area, stream chart, connected scatter",
      use: "Show change, trend, seasonality and movement over time.",
    },
    {
      family: "Hierarchy / part of whole",
      detected: schema.categorical,
      charts: "Treemap, sunburst, circular packing, doughnut or pie with caution",
      use: "Show composition or nested category structure.",
    },
    {
      family: "Network / flow",
      detected: schema.categorical,
      charts: "Sankey, chord diagram, network graph, arc diagram",
      use: "Show movement, relationships or transitions between entities.",
    },
    {
      family: "Map",
      detected: schema.categorical,
      charts: "Choropleth, bubble map, connection map",
      use: "Show values by place when geographic fields are present.",
    },
  ];

  chartguideTab.innerHTML = `
    <div class="section-heading">
      <p class="eyebrow">Chart selection guide</p>
      <h2>Recommended visualisation families</h2>
      <p>
        This guide is inspired by the From Data to Viz decision-tree approach:
        start from the data types you have, then choose charts that fit the question.
      </p>
      <p class="data-credit">
        Reference:
        <a href="https://www.data-to-viz.com/" target="_blank" rel="noopener noreferrer">
          From Data to Viz
        </a>
        by Yan Holtz and Conor Healy.
      </p>
    </div>

    <div class="chart-guide-grid">
      ${guideItems.map((item) => `
        <article class="chart-guide-card">
          <h3>${escapeHtml(item.family)}</h3>
          <p><strong>Detected fields:</strong> ${
            item.detected && item.detected.length
              ? item.detected.map(escapeHtml).join(", ")
              : "None detected"
          }</p>
          <p><strong>Possible charts:</strong> ${escapeHtml(item.charts)}</p>
          <p>${escapeHtml(item.use)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function drawChart(chartId, chart) {
  const layout = {
    margin: { t: 20, r: 20, b: 60, l: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      color: "#f5f7fb",
    },
  };

  const config = {
    responsive: true,
    displayModeBar: false,
  };

  if (chart.chart_type === "histogram") {
    Plotly.newPlot(chartId, [{
      x: chart.values,
      type: "histogram",
    }], layout, config);
    return;
  }

  if (chart.chart_type === "boxplot") {
    Plotly.newPlot(chartId, [{
      y: chart.values,
      type: "box",
      boxpoints: "outliers",
    }], layout, config);
    return;
  }

  if (["bar", "grouped_bar"].includes(chart.chart_type)) {
    Plotly.newPlot(chartId, [{
      x: chart.labels,
      y: chart.values,
      type: "bar",
    }], layout, config);
    return;
  }

  if (chart.chart_type === "line") {
    Plotly.newPlot(chartId, [{
      x: chart.labels,
      y: chart.values,
      type: "scatter",
      mode: "lines+markers",
    }], layout, config);
    return;
  }

  if (chart.chart_type === "correlation_heatmap") {
    const columns = chart.columns;
    const z = columns.map((rowCol) => {
      return columns.map((col) => chart.matrix[rowCol]?.[col] ?? null);
    });

    Plotly.newPlot(chartId, [{
      x: columns,
      y: columns,
      z,
      type: "heatmap",
      zmin: -1,
      zmax: 1,
    }], layout, config);
    return;
  }

  if (chart.chart_type === "scatter") {
    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      type: "scatter",
      mode: "markers",
      text: chart.columns.join(" vs "),
    }], {
      ...layout,
      xaxis: { title: chart.x_label },
      yaxis: { title: chart.y_label },
    }, config);
    return;
  }

  if (chart.chart_type === "bubble") {
    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      mode: "markers",
      type: "scatter",
      marker: {
        size: chart.size,
        sizemode: "diameter",
        opacity: 0.72,
      },
      text: chart.size_label,
    }], {
      ...layout,
      xaxis: { title: chart.x_label },
      yaxis: { title: chart.y_label },
    }, config);
    return;
  }

  if (chart.chart_type === "boxplot_by_category") {
    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      type: "box",
      boxpoints: "outliers",
    }], {
      ...layout,
      xaxis: { title: chart.x_label },
      yaxis: { title: chart.y_label },
    }, config);
    return;
  }

  if (chart.chart_type === "violin_by_category") {
    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      type: "violin",
      box: { visible: true },
      meanline: { visible: true },
      points: "outliers",
    }], {
      ...layout,
      xaxis: { title: chart.x_label },
      yaxis: { title: chart.y_label },
    }, config);
    return;
  }

  if (chart.chart_type === "stacked_bar") {
    const traces = chart.series.map((series) => ({
      x: chart.x_labels,
      y: series.values,
      name: series.name,
      type: "bar",
    }));

    Plotly.newPlot(chartId, traces, {
      ...layout,
      barmode: "stack",
      xaxis: { title: chart.x_label },
      yaxis: { title: "Count" },
      legend: {
        orientation: "h",
      },
    }, config);
    return;
  }

  if (chart.chart_type === "area") {
    Plotly.newPlot(chartId, [{
      x: chart.labels,
      y: chart.values,
      type: "scatter",
      mode: "lines",
      fill: "tozeroy",
    }], {
      ...layout,
      xaxis: { title: chart.columns[0] },
      yaxis: { title: chart.columns[1] },
    }, config);
    return;
  }

  if (chart.chart_type === "pca_scatter") {
    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      mode: "markers",
      type: "scatter",
      text: chart.hover,
      marker: {
        size: 10,
        opacity: 0.78,
        color: chart.colour,
      },
    }], {
      ...layout,
      xaxis: { title: chart.x_label },
      yaxis: { title: chart.y_label },
      legend: {
        orientation: "h",
      },
    }, config);
    return;
  }

  document.getElementById(chartId).innerHTML = `
    <p class="muted">Chart type not yet supported: ${escapeHtml(chart.chart_type)}</p>
  `;
}

function renderRelationships(analysis) {
  const relationships = analysis.relationships;
  const neighbours = analysis.nearest_neighbours;

  relationshipsTab.innerHTML = `
    <div class="analysis-card">
      <h3>Relationships and patterns</h3>
      <p>${escapeHtml(relationships.message || "")}</p>

      ${relationships.strong_correlations.length ? `
        <div class="insight-list">
          ${relationships.strong_correlations.map((item) => `
            <article class="insight-card">
              <h4>${escapeHtml(item.column_a)} ↔ ${escapeHtml(item.column_b)}</h4>
              <p>
                Correlation: <strong>${item.correlation}</strong>
                (${escapeHtml(item.strength)}, ${escapeHtml(item.direction)})
              </p>
            </article>
          `).join("")}
        </div>
      ` : `<p class="muted">No moderate or strong numeric correlations found yet.</p>`}
    </div>

    <div class="analysis-card">
      <h3>Nearest-neighbour analysis</h3>
      <p>${escapeHtml(neighbours.message || "")}</p>

      ${neighbours.available ? `
        <p><strong>Columns used:</strong> ${neighbours.columns_used.map(escapeHtml).join(", ")}</p>
        <div class="insight-list">
          ${neighbours.nearest_rows.map((row) => `
            <article class="insight-card">
              <h4>Row ${row.row_index}</h4>
              <p>Distance: ${row.distance}</p>
            </article>
          `).join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function renderRegressionMetrics(model) {
  return `
    <div class="analysis-card">
      <h3>Regression metrics</h3>
      <div class="results-grid">
        ${metricCard("MAE", model.mae)}
        ${metricCard("RMSE", model.rmse)}
        ${metricCard("R²", model.score)}
      </div>
    </div>
  `;
}

function renderConfusionMatrix(ml) {
  if (!ml.confusion_matrix || !ml.confusion_matrix.length) {
    return "";
  }

  const summary = confusionMatrixPlainEnglish(ml);

  return `
    <div class="analysis-card">
      <h3>Prediction breakdown</h3>

      <p>
        This table compares what actually happened with what the model predicted.
      </p>

      <p class="muted">
        Rows show the real value. Columns show the predicted value.
        Correct predictions are on the diagonal from top-left to bottom-right.
      </p>

      ${summary ? `<p>${summary}</p>` : ""}

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Actual \\ Predicted</th>
              ${ml.class_labels.map((label) => `<th>${escapeHtml(friendlyTargetValue(label, ml.target))}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${ml.confusion_matrix.map((row, index) => `
              <tr>
                <th>${escapeHtml(friendlyTargetValue(ml.class_labels[index], ml.target))}</th>
                ${row.map((value) => `<td>${value}</td>`).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderAdvanced(analysis) {
  const advanced = analysis.advanced;

  if (!advanced || !advanced.target_detected) {
    advancedTab.innerHTML = `
      <div class="analysis-card">
        <h3>Advanced EDA</h3>
        <p class="muted">${escapeHtml(advanced?.message || "No advanced analysis available yet.")}</p>
      </div>
    `;
    return;
  }

  advancedTab.innerHTML = `
    <div class="section-heading">
      <p class="eyebrow">Advanced EDA</p>
      <h2>Target and outcome analysis</h2>
      <p>${escapeHtml(advanced.message)}</p>
    </div>

    <div class="analysis-card">
      <h3>Target distribution</h3>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Target value</th>
              <th>Count</th>
              <th>%</th>
            </tr>
          </thead>
          <tbody>
            ${advanced.target_distribution.map((row) => `
              <tr>
                <td>${escapeHtml(row.target_value)}</td>
                <td>${row.count}</td>
                <td>${row.percent}%</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>

    ${renderTargetByCategory(advanced)}
    ${renderNumericByTarget(advanced)}
    ${renderSegmentationSummary(analysis.segmentation)}

  `;
}

function renderSegmentationSummary(segmentation) {
  if (!segmentation || !segmentation.available) {
    return `
      <div class="analysis-card">
        <h3>PCA and KMeans segmentation</h3>
        <p class="muted">${escapeHtml(segmentation?.message || "Segmentation is not available for this dataset.")}</p>
      </div>
    `;
  }

  return `
    <div class="analysis-card">
      <h3>PCA and KMeans segmentation</h3>
      <p>${escapeHtml(segmentation.message)}</p>

            <div class="results-grid">
              ${metricCard("Selected K", segmentation.selected_k)}
              ${metricCard("PC1 variance", `${segmentation.pca.explained_variance_pc1}%`)}
              ${metricCard("PC2 variance", `${segmentation.pca.explained_variance_pc2}%`)}
              ${metricCard("Total variance", `${segmentation.pca.total_explained_variance}%`)}
            </div>

            ${renderKMeansScores(segmentation)}
            ${renderPcaLoadings(segmentation)}

      <h4>Cluster profiles</h4>
      <div class="insight-list">
        ${segmentation.cluster_profiles.map((cluster) => `
          <article class="insight-card">
            <h4>Cluster ${cluster.cluster}</h4>
            <p><strong>Rows:</strong> ${cluster.count}</p>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Mean</th>
                    <th>Median</th>
                    <th>Min</th>
                    <th>Max</th>
                  </tr>
                </thead>
                <tbody>
                  ${cluster.numeric_summary.map((row) => `
                    <tr>
                      <td>${escapeHtml(row.column)}</td>
                      <td>${row.mean}</td>
                      <td>${row.median}</td>
                      <td>${row.min}</td>
                      <td>${row.max}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderTargetByCategory(advanced) {
  if (!advanced.target_by_category || !advanced.target_by_category.length) {
    return `
      <div class="analysis-card">
        <h3>Target by category</h3>
        <p class="muted">No suitable categorical comparisons found for this target.</p>
      </div>
    `;
  }

  return `
    <div class="analysis-card">
      <h3>Target by category</h3>
      <div class="insight-list">
        ${advanced.target_by_category.map((item) => `
          <article class="insight-card">
            <h4>${escapeHtml(item.target)} by ${escapeHtml(item.column)}</h4>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    ${item.analysis_type === "target_rate_by_category"
                      ? "<th>Target average</th><th>Count</th>"
                      : "<th>Most common target</th>"
                    }
                  </tr>
                </thead>
                <tbody>
                  ${item.rows.map((row) => `
                    <tr>
                      <td>${escapeHtml(row.category)}</td>
                      ${item.analysis_type === "target_rate_by_category"
                        ? `<td>${row.target_average}</td><td>${row.count}</td>`
                        : `<td>${escapeHtml(row.most_common_target)}</td>`
                      }
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderNumericByTarget(advanced) {
  if (!advanced.numeric_by_target || !advanced.numeric_by_target.length) {
    return `
      <div class="analysis-card">
        <h3>Numeric fields by target</h3>
        <p class="muted">No suitable numeric comparisons found for this target.</p>
      </div>
    `;
  }

  return `
    <div class="analysis-card">
      <h3>Numeric fields by target</h3>
      <div class="insight-list">
        ${advanced.numeric_by_target.map((item) => `
          <article class="insight-card">
            <h4>${escapeHtml(item.numeric_column)} by ${escapeHtml(item.target)}</h4>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Target value</th>
                    <th>Mean</th>
                    <th>Median</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  ${item.rows.map((row) => `
                    <tr>
                      <td>${escapeHtml(row.target_value)}</td>
                      <td>${row.mean}</td>
                      <td>${row.median}</td>
                      <td>${row.count}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderML(analysis) {
  const ml = analysis.ml;

  if (!ml || !ml.available) {
    mlTab.innerHTML = `
      <div class="analysis-card">
        <h3>ML / Prediction</h3>
        <p class="muted">${escapeHtml(ml?.message || "No prediction analysis is available for this dataset.")}</p>
      </div>
    `;
    return;
  }

  const bestModel = ml.best_model || {};
  const bestScoreName = friendlyMetricName(bestModel.score_name || "Score");

  mlTab.innerHTML = `
    <div class="section-heading">
      <p class="eyebrow">Prediction</p>
      <h2>Can the data predict an outcome?</h2>

      <p>
        CXMS found a likely outcome column:
        <strong>${escapeHtml(ml.target)}</strong>.
        It then tested whether the other usable columns could help predict that outcome.
      </p>

      <p class="muted">
        This is an early signal check, not a final production model.
        A good result here means the dataset may contain useful patterns worth investigating further.
      </p>
    </div>

    <div class="analysis-card">
      <h3>Best result</h3>

      <div class="results-grid">
        ${metricCard("Outcome predicted", ml.target)}
        ${metricCard("Prediction type", friendlyTaskType(ml.task_type))}
        ${metricCard("Best method", bestModel.name || "—")}
        ${metricCard(bestScoreName, bestModel.score ?? "—")}
        ${metricCard("Training rows", ml.train_rows)}
        ${metricCard("Test rows", ml.test_rows)}
      </div>

      <p class="muted">
        ${escapeHtml(metricPlainEnglish(bestModel.score_name, ml.task_type))}
      </p>
    </div>

    <div class="analysis-card">
      <h3>Which method worked best?</h3>
      <p>
        CXMS tested more than one prediction method and compared the scores on rows
        that were held back for testing.
      </p>
      <p class="muted">
        The model is trained on the training rows, then checked against the test rows.
        This gives a more realistic first view of whether the model has learned useful patterns.
      </p>

      ${renderModelComparison(ml)}
    </div>

    ${ml.task_type === "classification" ? renderConfusionMatrix(ml) : renderRegressionModelDetails(ml)}

    ${renderBestFeatureImportance(ml)}

    ${renderFeatureGroups(ml)}
  `;
}

function renderModelComparison(ml) {
  if (!ml.models || !ml.models.length) {
    return "";
  }

  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Method</th>
            <th>What it does</th>
            <th>Score</th>
            <th>Extra detail</th>
          </tr>
        </thead>
        <tbody>
          ${ml.models.map((model) => `
            <tr>
              <td>${escapeHtml(model.name)}</td>
              <td>${escapeHtml(modelPlainEnglish(model))}</td>
              <td>
                <strong>${escapeHtml(friendlyMetricName(model.score_name))}:</strong>
                ${model.score}
              </td>
              <td>
                ${model.mae !== undefined ? `Average error: ${model.mae}<br>` : ""}
                ${model.rmse !== undefined ? `Typical larger error: ${model.rmse}<br>` : ""}
                ${model.neighbours !== undefined ? `Similar rows used: ${model.neighbours}` : ""}
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>

    ${renderKnnScoresForML(ml)}
  `;
}

function renderKnnScoresForML(ml) {
  const knnModel = (ml.models || []).find((model) => model.k_scores && model.k_scores.length);

  if (!knnModel) {
    return "";
  }

  return `
    <h4>How the number of similar rows was chosen</h4>
    <p>
      K Nearest Neighbours works by looking at similar rows. CXMS tested several options
      and chose the number that gave the best score on the test data.
    </p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Similar rows tested</th>
            <th>${escapeHtml(friendlyMetricName(knnModel.score_name))}</th>
          </tr>
        </thead>
        <tbody>
          ${knnModel.k_scores.map((row) => `
            <tr>
              <td>${row.k}</td>
              <td>${row.score}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>

    <p class="muted">
      Selected value: <strong>${knnModel.neighbours}</strong>.
      If several options are tied, CXMS keeps the smaller value because it is simpler and more local.
    </p>
  `;
}

function renderBestFeatureImportance(ml) {
  const modelWithImportance = (ml.models || []).find((model) => model.feature_importance);

  if (!modelWithImportance) {
    return "";
  }

  return `
    <div class="analysis-card">
      <h3>Which fields seemed most useful?</h3>

      <p>
        This table shows which columns the Random Forest model relied on most when making predictions.
      </p>

      <p class="muted">
        A higher number means the field was more useful to the model.
        It does not mean the field caused the outcome.
      </p>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Usefulness score</th>
            </tr>
          </thead>
          <tbody>
            ${modelWithImportance.feature_importance.map((row) => `
              <tr>
                <td>${escapeHtml(friendlyFeatureName(row.feature))}</td>
                <td>${row.importance}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderFeatureGroups(ml) {
  const groups = ml.feature_groups || {};

  return `
    <div class="analysis-card">
      <h3>Fields used by the models</h3>

      <p>
        CXMS excluded likely IDs and long text fields, then used the fields that could be safely converted
        into model-friendly numbers.
      </p>

      <div class="insight-list">
        <article class="insight-card">
          <h4>Numbers</h4>
          <p class="muted">
            ${(groups.numeric || []).map(friendlyFeatureName).map(escapeHtml).join(", ") || "None"}
          </p>
        </article>

        <article class="insight-card">
          <h4>Yes / no fields</h4>
          <p class="muted">
            ${(groups.boolean || []).map(friendlyFeatureName).map(escapeHtml).join(", ") || "None"}
          </p>
        </article>

        <article class="insight-card">
          <h4>Categories converted for the model</h4>
          <p class="muted">
            ${(groups.categorical || []).map(friendlyFeatureName).map(escapeHtml).join(", ") || "None"}
          </p>
          <p class="muted">
            Machine learning models need categories such as Sex or Embarked to be converted into
            yes/no columns before they can use them.
          </p>
        </article>
      </div>
    </div>
  `;
}

function renderRegressionModelDetails(ml) {
  const bestModel = ml.best_model || {};

  return `
    <div class="analysis-card">
      <h3>Prediction error</h3>
      <p>
        This section shows how far away the number predictions were from the real values.
      </p>

      <div class="results-grid">
        ${metricCard("Average error", bestModel.mae ?? "—")}
        ${metricCard("Typical larger error", bestModel.rmse ?? "—")}
        ${metricCard("R² score", bestModel.score ?? "—")}
      </div>

      <p class="muted">
        Lower error values are better. R² is different: higher is better, and 1.0 would be a very strong fit.
      </p>
    </div>
  `;
}

function renderKMeansScores(segmentation) {
  if (!segmentation.k_scores || !segmentation.k_scores.length) {
    return "";
  }

  return `
    <h4>KMeans K selection</h4>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>K</th>
            <th>Inertia</th>
            <th>Silhouette</th>
          </tr>
        </thead>
        <tbody>
          ${segmentation.k_scores.map((row) => `
            <tr>
              <td>${row.k}</td>
              <td>${row.inertia}</td>
              <td>${row.silhouette}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPcaLoadings(segmentation) {
  const loadings = segmentation?.pca?.loadings;

  if (!loadings || !loadings.length) {
    return "";
  }

  return `
    <h4>PCA loadings</h4>
    <p class="muted">
      Loadings show which original numeric columns most strongly drive each principal component.
    </p>

    <div class="insight-list">
      ${loadings.map((component) => `
        <article class="insight-card">
          <h4>${escapeHtml(component.component)}</h4>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Loading</th>
                  <th>Direction</th>
                </tr>
              </thead>
              <tbody>
                ${component.top_drivers.slice(0, 8).map((row) => `
                  <tr>
                    <td>${escapeHtml(row.column)}</td>
                    <td>${row.loading}</td>
                    <td>${escapeHtml(row.direction)}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTheses(analysis) {
  thesesTab.innerHTML = `
    <div class="section-heading">
      <p class="eyebrow">Interpretation</p>
      <h2>Generated theses and improvement ideas</h2>
      <p>
        These are not final conclusions. They are suggested lines of investigation based on the structure and patterns in the data.
      </p>
    </div>

    <div class="insight-list">
      ${analysis.theses.map((thesis) => `
        <article class="insight-card thesis-card">
          <h3>${escapeHtml(thesis.title)}</h3>
          <p><strong>Evidence:</strong> ${escapeHtml(thesis.evidence)}</p>
          <p><strong>Input-level improvement:</strong> ${escapeHtml(thesis.input_level_improvement)}</p>
          <p><strong>Operational improvement:</strong> ${escapeHtml(thesis.operational_improvement)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function metricCard(label, value) {
  return `
    <article class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </article>
  `;
}

function schemaGroup(label, values) {
  return `
    <div class="schema-group">
      <h4>${escapeHtml(label)}</h4>
      <p>${values.length ? values.map(escapeHtml).join(", ") : "None detected"}</p>
    </div>
  `;
}

function valueOrDash(value) {
  return value === null || value === undefined ? "—" : value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function friendlyMetricName(metricName) {
  if (metricName === "accuracy") {
    return "Accuracy";
  }

  if (metricName === "R²") {
    return "R² score";
  }

  return metricName || "Score";
}


function friendlyFeatureName(name) {
  const knownNames = {
    Pclass: "Passenger class",
    SibSp: "Siblings/spouses aboard",
    Parch: "Parents/children aboard",
    Fare: "Fare paid",
    Age: "Age",
    has_cabin: "Cabin information present",
    Sex_male: "Sex = male",
    Sex_female: "Sex = female",
    Embarked_C: "Embarked = C",
    Embarked_Q: "Embarked = Q",
    Embarked_S: "Embarked = S",
    Embarked_Missing: "Embarked = missing",
  };

  return knownNames[name] || name.replaceAll("_", " ");
}

function friendlyTargetValue(value, targetName) {
  const target = String(targetName || "").toLowerCase();

  if (target === "survived") {
    if (String(value) === "0") return "Did not survive";
    if (String(value) === "1") return "Survived";
  }

  return String(value);
}


function confusionMatrixPlainEnglish(ml) {
  const matrix = ml.confusion_matrix;
  const labels = ml.class_labels || [];

  if (!matrix || matrix.length !== 2 || matrix[0].length !== 2 || labels.length !== 2) {
    return "";
  }

  const actual0 = friendlyTargetValue(labels[0], ml.target);
  const actual1 = friendlyTargetValue(labels[1], ml.target);

  const correct0 = matrix[0][0];
  const wrong0 = matrix[0][1];
  const wrong1 = matrix[1][0];
  const correct1 = matrix[1][1];

  return `
    The model correctly identified <strong>${correct0}</strong> rows as
    <strong>${escapeHtml(actual0)}</strong> and <strong>${correct1}</strong> rows as
    <strong>${escapeHtml(actual1)}</strong>.
    It got <strong>${wrong0 + wrong1}</strong> test rows wrong.
  `;
}


function modelPlainEnglish(model) {
  if (model.model_key === "knn_classifier" || model.model_key === "knn_regressor") {
    return "This model looks for rows that are most similar to the row it is trying to predict, then uses those similar rows to make a prediction.";
  }

  if (model.model_key === "random_forest_classifier" || model.model_key === "random_forest_regressor") {
    return "This model builds many small decision trees and combines their answers. It is useful because it can also estimate which fields were most helpful.";
  }

  return model.notes || "";
}


function friendlyTaskType(taskType) {
  if (taskType === "classification") {
    return "Category prediction";
  }

  if (taskType === "regression") {
    return "Number prediction";
  }

  return taskType || "Unknown";
}


function metricPlainEnglish(scoreName, taskType) {
  if (scoreName === "accuracy") {
    return "Accuracy means the percentage of test rows the model predicted correctly. For example, 0.80 means about 80% were correct.";
  }

  if (scoreName === "R²") {
    return "R² shows how well the model explains variation in a number. Higher is better, with 1.0 being a very strong fit.";
  }

  return "";
}
