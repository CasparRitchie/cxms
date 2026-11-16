import { activityLabels, coachingPrompt, conversionStages, monthlySeries, portfolioMetrics, projectStage, solutionBenefit, solutionStatus, stages } from "./domain.js";
import { users } from "./seed.js";

const state = { userId: users[0].id, view: "welcome", projectId: null, draftActivities: [] };
const app = document.querySelector("#app");

const money = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const date = (value) => value ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "Not yet";
const activeUser = () => users.find((user) => user.id === state.userId);

const navItems = [
  ["welcome", "Welcome"], ["contribution", "My contribution"], ["journey", "Improvement journey"],
  ["project", "Project detail"], ["add", "Add activity"], ["report", "Manager review"]
];

function shell(content) {
  const user = activeUser();
  return `<div class="shell">
    <aside class="sidebar">
      <div class="brand">Dash</div><div class="brand-note">Your evidence of workplace improvement, gathered over time.</div>
      <nav class="nav">${navItems.map(([id,label]) => `<button data-view="${id}" class="${state.view===id?"active":""}">${label}</button>`).join("")}</nav>
      <div class="sidebar-foot">Synthetic prototype data · No records are saved</div>
    </aside>
    <main class="main"><header class="topbar"><span class="eyebrow">Personal improvement journey</span>
      <select class="persona-select" aria-label="Choose demo persona">${users.map(item=>`<option value="${item.id}" ${item.id===user.id?"selected":""}>${item.name} · ${item.archetype}</option>`).join("")}</select>
    </header><div class="content">${content}</div></main>
  </div>`;
}

function welcome() {
  return `<section class="hero"><div class="eyebrow">Three prototype journeys</div><h1>Make better work visible.</h1>
    <p class="lede">Dash connects problems, improvement activity and credible results. Choose a demo persona to see how the same journey creates different guidance.</p></section>
    <div class="persona-grid">${users.map(user=>`<button class="persona-card" data-persona="${user.id}"><span>${user.archetype}</span><strong>${user.name}</strong><small>${user.role} · ${user.industry}</small><p>${user.profile}</p></button>`).join("")}</div>`;
}

function contribution() {
  const user = activeUser(), m = portfolioMetrics(user), prompt = coachingPrompt(user), series = monthlySeries(user);
  const max = Math.max(1, ...series.map(item=>item.problems+item.charters+item.solutions));
  return `<div class="page-head"><div><div class="eyebrow">${user.archetype}</div><h2>${user.name}'s contribution</h2><p>${user.profile}</p></div><button class="secondary" data-view="report">Build manager review</button></div>
    <div class="card-grid"><div class="card metric"><b>${m.projects}</b><span>Improvement projects</span></div><div class="card metric"><b>${m.implemented}</b><span>Solutions implemented</span></div><div class="card metric"><b>${money.format(m.annualValue)}</b><span>Estimated annual value</span></div></div>
    <div class="layout-two"><section class="panel"><h3>Activity over 12 months</h3><p class="lede">Problems, Charters/A3s and implementations recorded each month.</p><div class="spark">${series.map(item=>`<div class="bar-wrap"><div class="bar" style="height:${Math.max(4,(item.problems+item.charters+item.solutions)/max*110)}px"></div>${item.label}</div>`).join("")}</div></section>
    <section class="panel coach"><div class="eyebrow" style="color:#b8d94f">Recommended next action</div><h2>${prompt.title}</h2><p class="reason">${prompt.reason}</p><p>${prompt.action}</p><button class="primary" data-view="add">Record progress</button></section></div>`;
}

function journey() {
  const user=activeUser(), rows=conversionStages(user);
  return `<div class="page-head"><div><div class="eyebrow">From evidence to value</div><h2>Improvement journey</h2><p>Each bar shows how many identified problems have reached that stage. Gaps create explainable coaching prompts.</p></div></div>
    <section class="panel journey">${rows.map(row=>`<div class="journey-row"><span>${row.label}</span><div class="track"><span style="width:${row.rate*100}%"></span></div><b>${row.count}</b></div>`).join("")}</section>
    <div class="project-list">${user.projects.map(project=>`<button class="project-row" data-project="${project.id}"><div><strong>${project.title}</strong><p>${project.summary}</p></div><span class="badge">${stages.find(item=>item.id===projectStage(project)).label}</span></button>`).join("")}</div>`;
}

function projectDetail() {
  const user=activeUser();
  const project=user.projects.find(item=>item.id===state.projectId) || user.projects[0]; state.projectId=project.id;
  const events=[
    [project.identifiedAt,"Problem identified",project.summary],
    [project.charterDocumentedAt,project.charterType?`${project.charterType} documented`:"Charter / A3", project.charterType?"Problem and target documented.":"Not yet documented"],
    [project.sponsorEngagedAt,"Sponsor engaged",project.sponsorName || "No sponsor confirmed"],
    ...project.activities.map(item=>[item.date,activityLabels[item.type]||item.type, item.quantity>1?`${item.quantity} recorded`:"Completed"]),
    ...project.solutions.map(item=>[item.implementedAt,`Solution implemented: ${item.title}`,`${solutionStatus(item)} · ${number.format(solutionBenefit(item).weeklyHours)} hours/week`])
  ].filter(item=>item[0]).sort((a,b)=>new Date(a[0])-new Date(b[0]));
  return `<div class="page-head"><div><div class="eyebrow">${stages.find(item=>item.id===projectStage(project)).phase}</div><h2>${project.title}</h2><p>${project.summary}</p></div><button class="secondary" data-view="add">Add activity</button></div>
    <div class="layout-two"><section class="panel"><h3>Evidence timeline</h3><div class="timeline">${events.map(item=>`<div class="timeline-item"><strong>${item[1]}</strong><small>${date(item[0])}</small><p>${item[2]}</p></div>`).join("")}</div></section>
    <aside class="panel"><h3>Project context</h3><p><b>Charter:</b> ${project.charterType||"Not yet"}</p><p><b>Sponsor:</b> ${project.sponsorName||"Not confirmed"}</p><p><b>Current stage:</b> ${stages.find(item=>item.id===projectStage(project)).label}</p><p class="notice">This prototype derives the stage from evidence dates and activities; it does not ask for a dashboard score.</p></aside></div>`;
}

function addActivity() {
  const user=activeUser();
  return `<div class="page-head"><div><div class="eyebrow">Quick capture</div><h2>Record meaningful progress</h2><p>Add an event to its project. The dashboard will calculate the monthly gauge and next action.</p></div></div>
    <section class="panel"><form class="form" id="activity-form"><label>Project<select name="project">${user.projects.map(item=>`<option value="${item.id}">${item.title}</option>`).join("")}</select></label>
      <label>Activity<select name="type">${Object.entries(activityLabels).map(([id,label])=>`<option value="${id}">${label}</option>`).join("")}</select></label>
      <label>Date<input type="date" name="date" value="2026-11-16" required></label><label>What changed?<textarea name="note" placeholder="Add a short evidence note"></textarea></label>
      <div><button class="primary" type="submit">Add to this demo session</button></div><div class="notice">Demo entries remain only until this page is refreshed. No information is transmitted or stored.</div></form></section>
    ${state.draftActivities.length?`<section class="panel" style="margin-top:18px"><h3>Added this session</h3>${state.draftActivities.map(item=>`<p><b>${activityLabels[item.type]}</b> · ${date(item.date)}<br>${item.note||"No note"}</p>`).join("")}</section>`:""}`;
}

function report() {
  const user=activeUser(), m=portfolioMetrics(user), prompt=coachingPrompt(user);
  return `<div class="page-head"><div><div class="eyebrow">Controlled sharing</div><h2>Manager review</h2><p>Preview the evidence before choosing what to share. This does not grant permanent access to personal records.</p></div></div>
    <div class="report-controls"><select aria-label="Report period"><option>Last 6 months</option><option>Last 3 months</option><option>Last 12 months</option></select><button class="secondary" onclick="window.print()">Print preview</button></div>
    <article class="report"><div class="report-title"><div><small>Dash manager review</small><h2>${user.name}</h2><p>${user.role} · Last 6 months</p></div><div><b>${money.format(m.annualValue)}</b><br><small>Estimated annual value</small></div></div>
      <h3>Contribution summary</h3><table><thead><tr><th>Measure</th><th>Result</th><th>Evidence status</th></tr></thead><tbody>
      <tr><td>Charters / A3s</td><td>${m.charters}</td><td>Recorded</td></tr><tr><td>Solutions implemented</td><td>${m.implemented}</td><td>${m.validated} validated</td></tr><tr><td>Weekly team hours saved</td><td>${number.format(m.weeklyHours)}</td><td>${m.endorsed} sponsor-endorsed</td></tr></tbody></table>
      <h3 style="margin-top:28px">Discussion focus</h3><p><b>${prompt.title}.</b> ${prompt.reason} ${prompt.action}</p><h3 style="margin-top:28px">Projects included</h3>${user.projects.map(project=>`<p><b>${project.title}</b><br>${stages.find(item=>item.id===projectStage(project)).label}</p>`).join("")}
    </article>`;
}

const views={welcome,contribution,journey,project:projectDetail,add:addActivity,report};
function render(){ app.innerHTML=shell(views[state.view]()); bind(); }
function bind(){
  document.querySelectorAll("[data-view]").forEach(el=>el.addEventListener("click",()=>{state.view=el.dataset.view;render();}));
  document.querySelector(".persona-select")?.addEventListener("change",event=>{state.userId=event.target.value;state.projectId=null;render();});
  document.querySelectorAll("[data-persona]").forEach(el=>el.addEventListener("click",()=>{state.userId=el.dataset.persona;state.view="contribution";state.projectId=null;render();}));
  document.querySelectorAll("[data-project]").forEach(el=>el.addEventListener("click",()=>{state.projectId=el.dataset.project;state.view="project";render();}));
  document.querySelector("#activity-form")?.addEventListener("submit",event=>{event.preventDefault();const data=new FormData(event.target);state.draftActivities.unshift(Object.fromEntries(data));render();});
}
render();

