export const stages = [
  { id: "problem", label: "Problem identified", phase: "Define" },
  { id: "charter", label: "Charter / A3", phase: "Define" },
  { id: "sponsor", label: "Sponsor engaged", phase: "Define" },
  { id: "measure", label: "Process measured", phase: "Measure" },
  { id: "analyse", label: "Causes analysed", phase: "Analyse" },
  { id: "solution", label: "Solution implemented", phase: "Improve" },
  { id: "validated", label: "Result validated", phase: "Improve" },
  { id: "endorsed", label: "Sponsor endorsed", phase: "Control" },
  { id: "sustained", label: "Improvement sustained", phase: "Control" }
];

export const activityLabels = {
  sipoc: "SIPOC / systems map",
  process_map: "Process map",
  outputs_measured: "Outputs measured",
  failure_analysis: "Defects and rework analysis",
  brainstorming: "Brainstorming workshop",
  potential_solution: "Potential solution",
  cause_effect: "Cause-and-effect analysis",
  five_whys: "Five Whys",
  control_measure: "Control measure"
};

const hasDate = (value) => Boolean(value);
const activitiesOf = (project, types) =>
  project.activities.filter((activity) => types.includes(activity.type));

export function solutionStatus(solution) {
  if (hasDate(solution.sustainedAt)) return "Sustained";
  if (hasDate(solution.endorsedAt)) return "Endorsed";
  if (hasDate(solution.validatedAt)) return "Validated";
  if (hasDate(solution.implementedAt)) return "Implemented";
  return "Proposed";
}

export function solutionBenefit(solution) {
  const weeklyHours =
    (solution.hoursSavedPerPersonPerWeek || 0) * (solution.peopleAffected || 0);
  const annualValue = Math.round(weeklyHours * (solution.employeeCostPerHour || 0) * 52 * 100) / 100;
  return { weeklyHours, annualValue };
}

export function projectStage(project) {
  const solutions = project.solutions || [];
  if (solutions.some((item) => item.sustainedAt)) return "sustained";
  if (solutions.some((item) => item.endorsedAt)) return "endorsed";
  if (solutions.some((item) => item.validatedAt)) return "validated";
  if (solutions.some((item) => item.implementedAt)) return "solution";
  if (activitiesOf(project, ["brainstorming", "potential_solution", "cause_effect", "five_whys"]).length) return "analyse";
  if (activitiesOf(project, ["sipoc", "process_map", "outputs_measured", "failure_analysis"]).length) return "measure";
  if (project.sponsorEngagedAt) return "sponsor";
  if (project.charterDocumentedAt) return "charter";
  return "problem";
}

export function stageIndex(project) {
  return stages.findIndex((stage) => stage.id === projectStage(project));
}

export function portfolioMetrics(user) {
  const projects = user.projects;
  const allSolutions = projects.flatMap((project) => project.solutions || []);
  const implemented = allSolutions.filter((solution) => solution.implementedAt);
  const validated = allSolutions.filter((solution) => solution.validatedAt);
  const endorsed = allSolutions.filter((solution) => solution.endorsedAt);
  const benefits = implemented.map(solutionBenefit);
  return {
    projects: projects.length,
    charters: projects.filter((project) => project.charterDocumentedAt).length,
    sponsored: projects.filter((project) => project.sponsorEngagedAt).length,
    proposedSolutions: projects.reduce(
      (total, project) => total + activitiesOf(project, ["potential_solution"]).reduce((sum, item) => sum + (item.quantity || 1), 0),
      0
    ),
    implemented: implemented.length,
    validated: validated.length,
    endorsed: endorsed.length,
    weeklyHours: benefits.reduce((sum, item) => sum + item.weeklyHours, 0),
    annualValue: benefits.reduce((sum, item) => sum + item.annualValue, 0)
  };
}

export function conversionStages(user) {
  const projectCount = user.projects.length || 1;
  return stages.slice(0, 8).map((stage, index) => {
    const count = user.projects.filter((project) => stageIndex(project) >= index).length;
    return { ...stage, count, rate: count / projectCount };
  });
}

export function coachingPrompt(user) {
  const metrics = portfolioMetrics(user);
  const measured = user.projects.filter((project) => stageIndex(project) >= 3).length;
  const analysed = user.projects.filter((project) => stageIndex(project) >= 4).length;

  if (metrics.charters < Math.ceil(metrics.projects / 2)) {
    return {
      title: "Turn one problem into a clear A3",
      reason: `${metrics.projects - metrics.charters} identified problem${metrics.projects - metrics.charters === 1 ? " is" : "s are"} not yet documented.`,
      action: "Choose a problem and write the current condition, target and owner."
    };
  }
  if (metrics.sponsored < metrics.charters) {
    return {
      title: "Prepare a sponsor conversation",
      reason: `${metrics.charters - metrics.sponsored} documented project${metrics.charters - metrics.sponsored === 1 ? " has" : "s have"} no confirmed sponsor.`,
      action: "Share the problem, expected benefit and time required with your manager."
    };
  }
  if (measured && !metrics.proposedSolutions) {
    return {
      title: "Move from evidence to ideas",
      reason: "You have measured the process but have not recorded potential solutions.",
      action: "Run a short brainstorming or cause-and-effect session."
    };
  }
  if (analysed && metrics.implemented < analysed) {
    return {
      title: "Choose one idea to test",
      reason: `${analysed - metrics.implemented} analysed project${analysed - metrics.implemented === 1 ? " has" : "s have"} not reached implementation.`,
      action: "Prioritise a low-risk experiment and agree a measurement date."
    };
  }
  if (metrics.implemented > metrics.validated) {
    return {
      title: "Validate the result",
      reason: `${metrics.implemented - metrics.validated} implemented solution${metrics.implemented - metrics.validated === 1 ? " needs" : "s need"} before-and-after evidence.`,
      action: "Add the observed time, quality or customer outcome after implementation."
    };
  }
  if (metrics.validated > metrics.endorsed) {
    return {
      title: "Ask your sponsor to endorse the result",
      reason: "Validated evidence is ready for a manager review.",
      action: "Share the evidence and request confirmation of the benefit."
    };
  }
  return {
    title: "Sustain what is working",
    reason: "Your active projects have progressed through validation and endorsement.",
    action: "Confirm the control measure and review date for the strongest result."
  };
}

export function monthlySeries(user, months = 12) {
  const result = [];
  for (let offset = months - 1; offset >= 0; offset -= 1) {
    const date = new Date(Date.UTC(2026, 10 - offset, 1));
    const next = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1));
    const within = (value) => value && new Date(value) >= date && new Date(value) < next;
    result.push({
      key: date.toISOString().slice(0, 7),
      label: date.toLocaleString("en-GB", { month: "short", timeZone: "UTC" }),
      problems: user.projects.filter((project) => within(project.identifiedAt)).length,
      charters: user.projects.filter((project) => within(project.charterDocumentedAt)).length,
      solutions: user.projects.flatMap((project) => project.solutions).filter((solution) => within(solution.implementedAt)).length
    });
  }
  return result;
}

