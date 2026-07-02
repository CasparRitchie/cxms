const form = document.getElementById("interestForm");
const yearsSlider = document.getElementById("yearsSlider");
const yearsLabel = document.getElementById("yearsLabel");
const finalAmount = document.getElementById("finalAmount");
const gainText = document.getElementById("gainText");
const formulaExample = document.getElementById("formulaExample");
const compoundTable = document.getElementById("compoundTable");
const canvas = document.getElementById("compoundChart");
const ctx = canvas.getContext("2d");

function money(value) {
  return `£${Number(value).toFixed(2)}`;
}

function calculateRows(start, rate, years) {
  const rows = [{ year: 0, start, interest: 0, end: start }];

  let amount = start;

  for (let year = 1; year <= years; year += 1) {
    const interest = amount * rate;
    const end = amount + interest;

    rows.push({ year, start: amount, interest, end });
    amount = end;
  }

  return rows;
}

function drawChart(rows) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const padding = 40;
  const width = canvas.width - padding * 2;
  const height = canvas.height - padding * 2;

  const maxAmount = Math.max(...rows.map(row => row.end));
  const xStep = width / Math.max(1, rows.length - 1);

  ctx.beginPath();
  ctx.lineWidth = 3;

  rows.forEach((row, index) => {
    const x = padding + index * xStep;
    const y = canvas.height - padding - (row.end / maxAmount) * height;

    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });

  ctx.stroke();

  rows.forEach((row, index) => {
    const x = padding + index * xStep;
    const y = canvas.height - padding - (row.end / maxAmount) * height;

    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

function render() {
  const start = Number(form.initialInvestment.value || 0);
  const ratePercent = Number(form.annualRate.value || 0);
  const years = Number(form.years.value || 1);
  const rate = ratePercent / 100;
  const multiplier = 1 + rate;

  const rows = calculateRows(start, rate, years);
  const last = rows[rows.length - 1];
  const interestEarned = last.end - start;

  yearsLabel.textContent = `${years} year${years === 1 ? "" : "s"}`;
  finalAmount.textContent = money(last.end);
  gainText.textContent = `That means ${money(interestEarned)} interest has been earned.`;

  formulaExample.textContent =
    `${money(start)} × ${multiplier.toFixed(2)}^${years} = ${money(last.end)}`;

  compoundTable.innerHTML = `
    <div class="compound-table">
      <div class="compound-table-row compound-table-header">
        <span>Year</span>
        <span>Start</span>
        <span>Interest</span>
        <span>End</span>
      </div>

      ${rows.map(row => `
        <div class="compound-table-row">
          <span>${row.year}</span>
          <span>${money(row.start)}</span>
          <span>${row.year === 0 ? "-" : money(row.interest)}</span>
          <strong>${money(row.end)}</strong>
        </div>
      `).join("")}
    </div>
  `;

  drawChart(rows);
}

form.addEventListener("input", render);
render();
