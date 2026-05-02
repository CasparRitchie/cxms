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
      <h2>Charts</h2>
      <p>
        Use automatic charts for a fast overview, or switch to the manual explorer
        to choose your own chart type and fields.
      </p>
    </div>

    <div class="chart-mode-tabs" role="tablist" aria-label="Chart mode">
      <button class="chart-mode-tab active" data-chart-mode="auto">Auto charts</button>
      <button class="chart-mode-tab" data-chart-mode="manual">Manual explorer</button>
    </div>

    <div id="autoChartsPanel" class="chart-mode-panel active">
      <div class="section-heading compact-heading">
        <h3>Automatically recommended charts</h3>
        <p>
          These charts are selected automatically from the detected data types,
          inspired by the Data-to-Viz decision framework.
        </p>
      </div>
      <div id="chartGrid" class="chart-grid"></div>
    </div>

    <div id="manualChartsPanel" class="chart-mode-panel">
      ${renderManualChartExplorerShell(analysis)}
    </div>
  `;

  setupChartModeTabs();
  renderAutoCharts(analysis);
  setupManualChartExplorer(analysis);
}

function setupChartModeTabs() {
  document.querySelectorAll(".chart-mode-tab").forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.chartMode;

      document.querySelectorAll(".chart-mode-tab").forEach((tab) => {
        tab.classList.remove("active");
      });

      document.querySelectorAll(".chart-mode-panel").forEach((panel) => {
        panel.classList.remove("active");
      });

      button.classList.add("active");
      document.getElementById(`${mode}ChartsPanel`).classList.add("active");
    });
  });
}

function renderManualChartExplorerShell(analysis) {
  const schema = analysis.schema || {};
  const numericCols = schema.numeric || [];
  const categoricalCols = [
    ...(schema.categorical || []),
    ...(schema.boolean || []),
  ];
  const datetimeCols = schema.datetime || [];
  const allColumns = getAllManualColumns(analysis);

  return `
    <div class="manual-chart-explorer analysis-card">
      <h3>Manual chart explorer</h3>
      <p>
        Choose a chart type and the fields you want to explore. This uses a preview
        sample of the analysed data, so it updates quickly in the browser.
      </p>

      <div class="manual-chart-controls">
        ${selectControl("manualChartType", "Chart type", [
          ["histogram", "Histogram"],
          ["bar", "Bar chart"],
          ["scatter", "Scatter"],
          ["scatter_3d", "3D scatter"],
          ["bubble", "Bubble chart"],
          ["line", "Line chart"],
          ["area", "Area chart"],
          ["boxplot_by_category", "Boxplot by category"],
          ["violin_by_category", "Violin by category"],
          ["radar", "Radar chart"],
          ["treemap", "Treemap"],
          ["parallel_coordinates", "Parallel coordinates"],
        ])}

        ${selectControl("manualXColumn", "X / category", allColumns.map((col) => [col, friendlyFeatureName(col)]))}
        ${selectControl("manualYColumn", "Y / value", numericCols.map((col) => [col, friendlyFeatureName(col)]))}
        ${selectControl("manualZColumn", "Z axis", numericCols.map((col) => [col, friendlyFeatureName(col)]), true)}
        ${selectControl("manualColourColumn", "Colour / split by", categoricalCols.map((col) => [col, friendlyFeatureName(col)]), true)}
        ${selectControl("manualSizeColumn", "Size by", numericCols.map((col) => [col, friendlyFeatureName(col)]), true)}
      </div>

      <div id="manualChartHelp" class="manual-chart-help muted"></div>

      <div class="chart-card manual-chart-card">
        <div id="manualChartPreview" class="plotly-chart"></div>
      </div>

      <div class="manual-chart-notes">
        <p class="muted">
          Numeric fields detected: ${numericCols.length ? numericCols.map(escapeHtml).join(", ") : "none"}.
        </p>
        <p class="muted">
          Category fields detected: ${categoricalCols.length ? categoricalCols.map(escapeHtml).join(", ") : "none"}.
        </p>
      </div>
    </div>
  `;
}

function selectControl(id, label, options, includeNone = false) {
  return `
    <label class="manual-chart-control" for="${id}">
      <span>${escapeHtml(label)}</span>
      <select id="${id}">
        ${includeNone ? `<option value="">None</option>` : ""}
        ${options.map(([value, text]) => `
          <option value="${escapeHtml(value)}">${escapeHtml(text)}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function getAllManualColumns(analysis) {
  const schema = analysis.schema || {};

  return [
    ...(schema.numeric || []),
    ...(schema.categorical || []),
    ...(schema.boolean || []),
    ...(schema.datetime || []),
  ];
}

function renderAutoCharts(analysis) {
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

function setupManualChartExplorer(analysis) {
  const rows = analysis.preview_rows || [];

  if (!rows.length) {
    document.getElementById("manualChartPreview").innerHTML = `
      <p class="muted">No preview rows are available for manual charting.</p>
    `;
    return;
  }

  const controls = [
    "manualChartType",
    "manualXColumn",
    "manualYColumn",
    "manualZColumn",
    "manualColourColumn",
    "manualSizeColumn",
  ];

  controls.forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      element.addEventListener("change", () => drawManualChart(analysis));
    }
  });

  setInitialManualChartSelections(analysis);
  drawManualChart(analysis);
}

function setInitialManualChartSelections(analysis) {
  const schema = analysis.schema || {};
  const numericCols = schema.numeric || [];
  const categoricalCols = [
    ...(schema.categorical || []),
    ...(schema.boolean || []),
  ];

  setSelectValue("manualChartType", numericCols.length >= 2 ? "scatter" : "bar");

  if (numericCols[0]) setSelectValue("manualXColumn", numericCols[0]);
  if (numericCols[1]) setSelectValue("manualYColumn", numericCols[1]);
  if (numericCols[2]) setSelectValue("manualZColumn", numericCols[2]);
  if (categoricalCols[0]) setSelectValue("manualColourColumn", categoricalCols[0]);

  if (!numericCols.length && categoricalCols[0]) {
    setSelectValue("manualXColumn", categoricalCols[0]);
  }
}

function setSelectValue(id, value) {
  const element = document.getElementById(id);

  if (!element) {
    return;
  }

  const optionExists = Array.from(element.options).some((option) => option.value === value);

  if (optionExists) {
    element.value = value;
  }
}

function drawManualChart(analysis) {
  const rows = analysis.preview_rows || [];

  const chartType = getSelectValue("manualChartType");
  const xCol = getSelectValue("manualXColumn");
  const yCol = getSelectValue("manualYColumn");
  const zCol = getSelectValue("manualZColumn");
  const colourCol = getSelectValue("manualColourColumn");
  const sizeCol = getSelectValue("manualSizeColumn");

  const helpEl = document.getElementById("manualChartHelp");

  if (helpEl) {
    helpEl.textContent = manualChartHelpText(chartType);
  }

  const chart = buildManualChartConfig({
    chartType,
    rows,
    xCol,
    yCol,
    zCol,
    colourCol,
    sizeCol,
  });

  if (!chart) {
    document.getElementById("manualChartPreview").innerHTML = `
      <p class="muted">Choose suitable fields for this chart type.</p>
    `;
    return;
  }

  drawChart("manualChartPreview", chart);
}

function buildManualChartConfig({ chartType, rows, xCol, yCol, zCol, colourCol, sizeCol }) {
  if (!rows.length) {
    return null;
  }

  if (chartType === "histogram") {
    const column = yCol || xCol;
    const values = numericValues(rows, column);

    if (!column || !values.length) {
      return null;
    }

    return {
      title: `Distribution of ${column}`,
      chart_type: "histogram",
      phase: "manual",
      columns: [column],
      values,
      why: `Shows the spread of values in ${column}.`,
    };
  }

  if (chartType === "bar") {
    const column = xCol;
    const counts = countByCategory(rows, column);

    if (!column || !counts.labels.length) {
      return null;
    }

    return {
      title: `Category counts for ${column}`,
      chart_type: "bar",
      phase: "manual",
      columns: [column],
      labels: counts.labels,
      values: counts.values,
      why: `Shows how many rows appear in each ${column} category.`,
    };
  }

  if (chartType === "scatter") {
    if (!xCol || !yCol) {
      return null;
    }

    const points = pairedNumericValues(rows, xCol, yCol, colourCol, sizeCol);

    if (!points.x.length) {
      return null;
    }

    return {
      title: `${yCol} vs ${xCol}`,
      chart_type: "scatter",
      phase: "manual",
      columns: [xCol, yCol],
      x: points.x,
      y: points.y,
      colour: points.colour,
      colour_label: colourCol || null,
      colour_tick_vals: points.colour_tick_vals,
      colour_tick_text: points.colour_tick_text,
      size: points.size,
      size_label: sizeCol || null,
      hover: points.hover,
      x_label: xCol,
      y_label: yCol,
      why: "Shows the relationship between two numeric fields. Colour and point size can add extra context.",
    };
  }

  if (chartType === "scatter_3d") {
    if (!xCol || !yCol || !zCol) {
      return null;
    }

    const points = tripleNumericValues(rows, xCol, yCol, zCol, colourCol, sizeCol);

    if (!points.x.length) {
      return null;
    }

    return {
      title: `3D view: ${xCol}, ${yCol} and ${zCol}`,
      chart_type: "scatter_3d",
      phase: "manual",
      columns: [xCol, yCol, zCol],
      x: points.x,
      y: points.y,
      z: points.z,
      colour: points.colour,
      colour_label: colourCol || null,
      colour_tick_vals: points.colour_tick_vals,
      colour_tick_text: points.colour_tick_text,
      size: points.size,
      size_label: sizeCol || null,
      hover: points.hover,
      x_label: xCol,
      y_label: yCol,
      z_label: zCol,
      why: "Shows three numeric fields at the same time. You can rotate and zoom the chart.",
    };
  }

  if (chartType === "bubble") {
    if (!xCol || !yCol || !sizeCol) {
      return null;
    }

    const points = pairedNumericValues(rows, xCol, yCol, colourCol, sizeCol);

    if (!points.x.length) {
      return null;
    }

    return {
      title: `${yCol} vs ${xCol}, sized by ${sizeCol}`,
      chart_type: "bubble",
      phase: "manual",
      columns: [xCol, yCol, sizeCol],
      x: points.x,
      y: points.y,
      size: points.size,
      colour: points.colour,
      colour_label: colourCol || null,
      colour_tick_vals: points.colour_tick_vals,
      colour_tick_text: points.colour_tick_text,
      hover: points.hover,
      x_label: xCol,
      y_label: yCol,
      size_label: sizeCol,
      why: "Shows two numeric fields, with point size adding a third numeric measure.",
    };
  }

  if (chartType === "line" || chartType === "area") {
    if (!xCol || !yCol) {
      return null;
    }

    const points = pairedAnyXNumericYValues(rows, xCol, yCol);

    if (!points.x.length) {
      return null;
    }

    return {
      title: `${yCol} by ${xCol}`,
      chart_type: chartType,
      phase: "manual",
      columns: [xCol, yCol],
      labels: points.x,
      values: points.y,
      why: chartType === "line"
        ? "Shows how a numeric value changes across an ordered field."
        : "Shows the size and movement of a numeric value across an ordered field.",
    };
  }

  if (chartType === "radar") {
    if (!xCol) {
      return null;
    }

    return buildManualRadarChart(rows, xCol, [yCol, zCol, sizeCol].filter(Boolean));
  }

  if (chartType === "boxplot_by_category" || chartType === "violin_by_category") {
    if (!xCol || !yCol) {
      return null;
    }

    const points = categoryNumericValues(rows, xCol, yCol);

    if (!points.x.length) {
      return null;
    }

    return {
      title: `${yCol} by ${xCol}`,
      chart_type: chartType,
      phase: "manual",
      columns: [xCol, yCol],
      x: points.x,
      y: points.y,
      x_label: xCol,
      y_label: yCol,
      why: "Compares the distribution of a numeric field across categories.",
    };
  }

  if (chartType === "treemap") {
    if (!xCol) {
      return null;
    }

    return buildManualTreemapChart(rows, xCol, colourCol, yCol);
  }

  if (chartType === "parallel_coordinates") {
    return buildManualParallelCoordinatesChart(rows, [xCol, yCol, zCol, sizeCol].filter(Boolean), colourCol);
  }

  return null;
}

function numericValues(rows, column, limit = 1000) {
  if (!column) return [];

  return rows
    .map((row) => Number(row[column]))
    .filter((value) => Number.isFinite(value))
    .slice(0, limit);
}

function pairedNumericValues(rows, xCol, yCol, colourCol = "", sizeCol = "", limit = 1000) {
  const cleanRows = [];

  rows.forEach((row) => {
    if (cleanRows.length >= limit) return;

    const xValue = Number(row[xCol]);
    const yValue = Number(row[yCol]);

    if (Number.isFinite(xValue) && Number.isFinite(yValue)) {
      cleanRows.push(row);
    }
  });

  const x = cleanRows.map((row) => Number(row[xCol]));
  const y = cleanRows.map((row) => Number(row[yCol]));

  const hover = cleanRows.map((row, index) => {
    const parts = [
      `${xCol}: ${row[xCol]}`,
      `${yCol}: ${row[yCol]}`,
    ];

    if (colourCol) {
      parts.push(`${colourCol}: ${row[colourCol] ?? "Missing"}`);
    }

    if (sizeCol) {
      parts.push(`${sizeCol}: ${row[sizeCol] ?? "Missing"}`);
    }

    return parts.join("<br>");
  });

  let colour = null;
  let colour_tick_vals = null;
  let colour_tick_text = null;

  if (colourCol) {
    const encoded = encodeCategories(cleanRows.map((row) => row[colourCol]));
    colour = encoded.values;
    colour_tick_vals = encoded.tickVals;
    colour_tick_text = encoded.tickText;
  }

  let size = null;

  if (sizeCol) {
    size = scaledMarkerSizes(cleanRows.map((row) => row[sizeCol]));
  }

  return {
    x,
    y,
    colour,
    colour_tick_vals,
    colour_tick_text,
    size,
    hover,
  };
}

function tripleNumericValues(rows, xCol, yCol, zCol, colourCol = "", sizeCol = "", limit = 1000) {
  const cleanRows = [];

  rows.forEach((row) => {
    if (cleanRows.length >= limit) return;

    const xValue = Number(row[xCol]);
    const yValue = Number(row[yCol]);
    const zValue = Number(row[zCol]);

    if (Number.isFinite(xValue) && Number.isFinite(yValue) && Number.isFinite(zValue)) {
      cleanRows.push(row);
    }
  });

  const x = cleanRows.map((row) => Number(row[xCol]));
  const y = cleanRows.map((row) => Number(row[yCol]));
  const z = cleanRows.map((row) => Number(row[zCol]));

  const hover = cleanRows.map((row) => {
    const parts = [
      `${xCol}: ${row[xCol]}`,
      `${yCol}: ${row[yCol]}`,
      `${zCol}: ${row[zCol]}`,
    ];

    if (colourCol) {
      parts.push(`${colourCol}: ${row[colourCol] ?? "Missing"}`);
    }

    if (sizeCol) {
      parts.push(`${sizeCol}: ${row[sizeCol] ?? "Missing"}`);
    }

    return parts.join("<br>");
  });

  let colour = z;
  let colour_tick_vals = null;
  let colour_tick_text = null;

  if (colourCol) {
    const encoded = encodeCategories(cleanRows.map((row) => row[colourCol]));
    colour = encoded.values;
    colour_tick_vals = encoded.tickVals;
    colour_tick_text = encoded.tickText;
  }

  const size = sizeCol
    ? scaledMarkerSizes(cleanRows.map((row) => row[sizeCol]))
    : null;

  return {
    x,
    y,
    z,
    colour,
    colour_tick_vals,
    colour_tick_text,
    size,
    hover,
  };
}

function categoryNumericValues(rows, categoryCol, numericCol, limit = 1000) {
  const x = [];
  const y = [];

  rows.forEach((row) => {
    if (x.length >= limit) return;

    const categoryValue = row[categoryCol];
    const numericValue = Number(row[numericCol]);

    if (categoryValue !== null && categoryValue !== undefined && Number.isFinite(numericValue)) {
      x.push(String(categoryValue));
      y.push(numericValue);
    }
  });

  return { x, y };
}

function countByCategory(rows, column, limit = 20) {
  const counts = new Map();

  rows.forEach((row) => {
    const value = row[column] === null || row[column] === undefined || row[column] === ""
      ? "Missing"
      : String(row[column]);

    counts.set(value, (counts.get(value) || 0) + 1);
  });

  const sorted = Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);

  return {
    labels: sorted.map(([label]) => label),
    values: sorted.map(([, value]) => value),
  };
}

function pairedAnyXNumericYValues(rows, xCol, yCol, limit = 1000) {
  const pairs = [];

  rows.forEach((row) => {
    if (pairs.length >= limit) return;

    const yValue = Number(row[yCol]);

    if (row[xCol] !== null && row[xCol] !== undefined && Number.isFinite(yValue)) {
      pairs.push({
        x: String(row[xCol]),
        y: yValue,
      });
    }
  });

  return {
    x: pairs.map((row) => row.x),
    y: pairs.map((row) => row.y),
  };
}

function buildManualRadarChart(rows, categoryCol, numericColumns) {
  const usableNumericColumns = numericColumns.filter(Boolean).slice(0, 6);

  if (!categoryCol || usableNumericColumns.length < 3) {
    return null;
  }

  const groups = new Map();

  rows.forEach((row) => {
    const category = row[categoryCol] === null || row[categoryCol] === undefined || row[categoryCol] === ""
      ? "Missing"
      : String(row[categoryCol]);

    if (!groups.has(category)) {
      groups.set(category, []);
    }

    groups.get(category).push(row);
  });

  const largestGroups = Array.from(groups.entries())
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 6);

  if (largestGroups.length < 2) {
    return null;
  }

  const rawSeries = largestGroups.map(([groupName, groupRows]) => {
    const values = usableNumericColumns.map((column) => {
      const nums = groupRows
        .map((row) => Number(row[column]))
        .filter((value) => Number.isFinite(value));

      if (!nums.length) return null;

      return nums.reduce((sum, value) => sum + value, 0) / nums.length;
    });

    return {
      name: groupName,
      values,
    };
  });

  const normalisedSeries = normaliseRadarSeries(rawSeries);

  return {
    title: `Radar profile by ${categoryCol}`,
    chart_type: "radar",
    phase: "manual",
    columns: [categoryCol, ...usableNumericColumns],
    variables: usableNumericColumns,
    series: normalisedSeries,
    why: "Compares average numeric profiles across category groups. Values are scaled from 0 to 1 so different units can be shown together.",
  };
}

function normaliseRadarSeries(series) {
  if (!series.length) return [];

  const variableCount = series[0].values.length;
  const mins = [];
  const maxes = [];

  for (let index = 0; index < variableCount; index += 1) {
    const values = series
      .map((row) => row.values[index])
      .filter((value) => Number.isFinite(value));

    mins[index] = values.length ? Math.min(...values) : 0;
    maxes[index] = values.length ? Math.max(...values) : 0;
  }

  return series.map((row) => ({
    name: row.name,
    values: row.values.map((value, index) => {
      if (!Number.isFinite(value)) return 0;

      const min = mins[index];
      const max = maxes[index];

      if (min === max) return 0.5;

      return (value - min) / (max - min);
    }),
    raw_values: row.values,
  }));
}

function encodeCategories(values) {
  const labels = values.map((value) => {
    if (value === null || value === undefined || value === "") {
      return "Missing";
    }

    return String(value);
  });

  const uniqueLabels = Array.from(new Set(labels));
  const labelToNumber = new Map(
    uniqueLabels.map((label, index) => [label, index])
  );

  return {
    values: labels.map((label) => labelToNumber.get(label)),
    tickVals: uniqueLabels.map((_, index) => index),
    tickText: uniqueLabels,
  };
}

function scaledMarkerSizes(values, minSize = 7, maxSize = 24) {
  const numericValues = values.map((value) => Number(value));
  const finiteValues = numericValues.filter((value) => Number.isFinite(value));

  if (!finiteValues.length) {
    return null;
  }

  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);

  if (min === max) {
    return numericValues.map((value) => Number.isFinite(value) ? 12 : 7);
  }

  return numericValues.map((value) => {
    if (!Number.isFinite(value)) {
      return minSize;
    }

    return minSize + ((value - min) / (max - min)) * (maxSize - minSize);
  });
}

function buildManualTreemapChart(rows, parentCol, childCol, valueCol) {
  const labels = [];
  const parents = [];
  const ids = [];
  const values = [];

  const hasChild = Boolean(childCol);
  const hasValue = Boolean(valueCol);

  if (!hasChild) {
    const counts = countByCategory(rows, parentCol, 30);

    counts.labels.forEach((label, index) => {
      labels.push(label);
      parents.push("");
      ids.push(label);
      values.push(counts.values[index]);
    });

    return {
      title: `Treemap by ${parentCol}`,
      chart_type: "treemap",
      phase: "manual",
      columns: [parentCol],
      ids,
      labels,
      parents,
      values,
      value_label: "Row count",
      why: "Shows how rows are split across categories.",
    };
  }

  const grouped = new Map();
  const parentTotals = new Map();

  rows.forEach((row) => {
    const parentValue = row[parentCol] === null || row[parentCol] === undefined || row[parentCol] === ""
      ? "Missing"
      : String(row[parentCol]);

    const childValue = row[childCol] === null || row[childCol] === undefined || row[childCol] === ""
      ? "Missing"
      : String(row[childCol]);

    const numericValue = hasValue ? Number(row[valueCol]) : 1;
    const value = Number.isFinite(numericValue) ? numericValue : 0;

    const key = `${parentValue}/${childValue}`;

    grouped.set(key, {
      parent: parentValue,
      child: childValue,
      value: (grouped.get(key)?.value || 0) + value,
    });

    parentTotals.set(parentValue, (parentTotals.get(parentValue) || 0) + value);
  });

  Array.from(grouped.values()).forEach((item) => {
    labels.push(item.child);
    parents.push(item.parent);
    ids.push(`${item.parent}/${item.child}`);
    values.push(item.value);
  });

  Array.from(parentTotals.entries()).forEach(([parent, total]) => {
    labels.push(parent);
    parents.push("");
    ids.push(parent);
    values.push(total);
  });

  return {
    title: `Treemap by ${parentCol} → ${childCol}`,
    chart_type: "treemap",
    phase: "manual",
    columns: [parentCol, childCol, valueCol].filter(Boolean),
    ids,
    labels,
    parents,
    values,
    value_label: hasValue ? `Sum of ${valueCol}` : "Row count",
    why: "Shows composition across one or two category levels.",
  };
}

function buildManualParallelCoordinatesChart(rows, selectedColumns, colourCol) {
  const numericColumns = selectedColumns.filter(Boolean).slice(0, 6);

  if (numericColumns.length < 3) {
    return null;
  }

  const cleanRows = rows.filter((row) => {
    return numericColumns.every((column) => Number.isFinite(Number(row[column])));
  }).slice(0, 1000);

  if (cleanRows.length < 10) {
    return null;
  }

  const dimensions = numericColumns.map((column) => ({
    label: column,
    values: cleanRows.map((row) => Number(row[column])),
  }));

  let colour = null;
  let colourLabel = null;
  let colourTickVals = null;
  let colourTickText = null;

  if (colourCol) {
    const categories = Array.from(new Set(cleanRows.map((row) => String(row[colourCol] ?? "Missing"))));
    const categoryToNumber = new Map(categories.map((category, index) => [category, index]));

    colour = cleanRows.map((row) => categoryToNumber.get(String(row[colourCol] ?? "Missing")));
    colourLabel = colourCol;
    colourTickVals = categories.map((_, index) => index);
    colourTickText = categories;
  }

  return {
    title: "Parallel coordinates view",
    chart_type: "parallel_coordinates",
    phase: "manual",
    columns: numericColumns,
    dimensions,
    colour,
    colour_label: colourLabel,
    colour_tick_vals: colourTickVals,
    colour_tick_text: colourTickText,
    why: "Shows several numeric fields at once. Each line is one row.",
  };
}

function getSelectValue(id) {
  const element = document.getElementById(id);
  return element ? element.value : "";
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
    const marker = {
      size: chart.size || 9,
      opacity: 0.78,
    };

    if (chart.colour) {
      marker.color = chart.colour;
      marker.colorscale = "Viridis";
      marker.showscale = true;
      marker.colorbar = {
        title: chart.colour_label ? friendlyFeatureName(chart.colour_label) : "Colour",
        tickvals: chart.colour_tick_vals || undefined,
        ticktext: chart.colour_tick_text || undefined,
      };
    }

    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      type: "scatter",
      mode: "markers",
      text: chart.hover || chart.columns.join(" vs "),
      hovertemplate: "%{text}<extra></extra>",
      marker,
    }], {
      ...layout,
      xaxis: { title: chart.x_label },
      yaxis: { title: chart.y_label },
    }, config);

    return;
  }

  if (chart.chart_type === "scatter_3d") {
    const trace = {
      x: chart.x,
      y: chart.y,
      z: chart.z,
      mode: "markers",
      type: "scatter3d",
      text: chart.hover,
      hovertemplate: "%{text}<extra></extra>",
      marker: {
        size: chart.size || 4,
        opacity: 0.78,
        color: chart.colour || chart.z,
        colorscale: "Viridis",
        showscale: Boolean(chart.colour_label),
        colorbar: {
          title: chart.colour_label ? friendlyFeatureName(chart.colour_label) : "Value",
          tickvals: chart.colour_tick_vals || undefined,
          ticktext: chart.colour_tick_text || undefined,
        },
      },
    };

    Plotly.newPlot(chartId, [trace], {
      ...layout,
      scene: {
        xaxis: { title: chart.x_label },
        yaxis: { title: chart.y_label },
        zaxis: { title: chart.z_label },
      },
      margin: { t: 20, r: 20, b: 20, l: 20 },
    }, config);
    return;
  }

  if (chart.chart_type === "bubble") {
    const marker = {
      size: chart.size,
      sizemode: "diameter",
      opacity: 0.72,
    };

    if (chart.colour) {
      marker.color = chart.colour;
      marker.colorscale = "Viridis";
      marker.showscale = true;
      marker.colorbar = {
        title: chart.colour_label ? friendlyFeatureName(chart.colour_label) : "Colour",
        tickvals: chart.colour_tick_vals || undefined,
        ticktext: chart.colour_tick_text || undefined,
      };
    }

    Plotly.newPlot(chartId, [{
      x: chart.x,
      y: chart.y,
      mode: "markers",
      type: "scatter",
      marker,
      text: chart.hover || chart.size_label,
      hovertemplate: "%{text}<extra></extra>",
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

  if (chart.chart_type === "radar") {
    const variables = [...chart.variables, chart.variables[0]];

    const traces = chart.series.map((series) => {
      const values = [...series.values, series.values[0]];

      return {
        type: "scatterpolar",
        r: values,
        theta: variables,
        fill: "toself",
        name: series.name,
      };
    });

    Plotly.newPlot(chartId, traces, {
      ...layout,
      polar: {
        radialaxis: {
          visible: true,
          range: [0, 1],
        },
      },
      showlegend: true,
    }, config);
    return;
  }

  if (chart.chart_type === "treemap") {
    Plotly.newPlot(chartId, [{
      type: "treemap",
      ids: chart.ids,
      labels: chart.labels,
      parents: chart.parents,
      values: chart.values,
      textinfo: "label+value+percent parent",
      hovertemplate: `<b>%{label}</b><br>${escapeHtml(chart.value_label || "Value")}: %{value}<extra></extra>`,
    }], {
      ...layout,
      margin: { t: 20, r: 20, b: 20, l: 20 },
    }, config);
    return;
  }

  if (chart.chart_type === "parallel_coordinates") {
    const trace = {
      type: "parcoords",
      dimensions: chart.dimensions.map((dimension) => ({
        label: friendlyFeatureName(dimension.label),
        values: dimension.values,
      })),
      line: {
        color: chart.colour || chart.dimensions[0].values,
        showscale: true,
        colorbar: {
          title: chart.colour_label ? friendlyFeatureName(chart.colour_label) : "Value",
          tickvals: chart.colour_tick_vals || undefined,
          ticktext: chart.colour_tick_text || undefined,
        },
      },
    };

    Plotly.newPlot(chartId, [trace], {
      ...layout,
      margin: { t: 30, r: 80, b: 30, l: 60 },
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

function manualChartHelpText(chartType) {
  const help = {
    histogram: "Use a histogram to see the spread of one numeric field. Use Y / value to choose the field.",
    bar: "Use a bar chart to count rows in each category. Use X / category to choose the category.",
    scatter: "Use a scatter chart to compare two numeric fields. Colour and size can add extra context. Z axis is only used by 3D scatter.",
    scatter_3d: "Use a 3D scatter chart to compare three numeric fields. X, Y and Z are all used. Colour and size can add extra context.",
    bubble: "Use a bubble chart when you want X and Y to show two numeric fields, while point size shows a third numeric field.",
    line: "Use a line chart when the X field has a useful order, such as date, month, year, rank or sequence.",
    area: "Use an area chart like a line chart, but with the space underneath filled to emphasise size and movement.",
    radar: "Use a radar chart to compare the average profile of groups across several numeric fields.",
    boxplot_by_category: "Use a boxplot to compare the spread of a numeric field across categories. X is the category and Y is the number.",
    violin_by_category: "Use a violin chart to compare distribution shape across categories. X is the category and Y is the number.",
    treemap: "Use a treemap to show part-of-whole composition. X is the main category and Colour / split by becomes the second category.",
    parallel_coordinates: "Use parallel coordinates to compare several numeric fields at once. X, Y, Z and Size by become numeric dimensions.",
  };

  return help[chartType] || "";
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
