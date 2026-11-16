const activity = (type, date, quantity = 1) => ({ type, date, quantity });
const solution = (id, implementedAt, options = {}) => ({
  id,
  title: options.title || "Improvement",
  implementedAt,
  validatedAt: options.validatedAt || null,
  endorsedAt: options.endorsedAt || null,
  sustainedAt: options.sustainedAt || null,
  hoursSavedPerPersonPerWeek: options.hours ?? 0.25,
  peopleAffected: options.people ?? 5,
  employeeCostPerHour: options.cost ?? 72.82
});

export const users = [
  {
    id: "user-1",
    name: "Alex Morgan",
    archetype: "Consistent improver",
    role: "Operations",
    industry: "Banking and financial services",
    organisationSize: "Medium",
    profile: "Builds momentum from problem identification through measurable, endorsed results.",
    projects: [
      {
        id: "u1-p1", title: "Reduce customer hand-off delays", summary: "Repeated hand-offs slow urgent customer requests.", status: "Active",
        identifiedAt: "2026-02-04", charterType: "A3", charterDocumentedAt: "2026-02-12", sponsorName: "Jordan Lee", sponsorEngagedAt: "2026-02-18",
        activities: [activity("sipoc", "2026-03-03"), activity("process_map", "2026-03-10"), activity("outputs_measured", "2026-03-24"), activity("brainstorming", "2026-04-08"), activity("potential_solution", "2026-04-08", 4), activity("cause_effect", "2026-04-14")],
        solutions: [solution("u1-s1", "2026-05-06", { title: "Single hand-off checklist", validatedAt: "2026-06-10", endorsedAt: "2026-06-18", sustainedAt: "2026-09-15" })]
      },
      {
        id: "u1-p2", title: "Prevent avoidable case rework", summary: "Incomplete submissions create repeated checking and re-entry.", status: "Active",
        identifiedAt: "2026-05-11", charterType: "Charter", charterDocumentedAt: "2026-05-20", sponsorName: "Taylor Smith", sponsorEngagedAt: "2026-05-26",
        activities: [activity("process_map", "2026-06-02"), activity("failure_analysis", "2026-06-15"), activity("five_whys", "2026-06-20"), activity("potential_solution", "2026-06-20", 3)],
        solutions: [solution("u1-s2", "2026-07-07", { title: "Pre-submission quality prompt", validatedAt: "2026-08-12", endorsedAt: "2026-08-20", hours: 0.35, people: 6 })]
      },
      {
        id: "u1-p3", title: "Shorten exception review", summary: "Low-risk exceptions wait in the same queue as complex cases.", status: "Active",
        identifiedAt: "2026-08-03", charterType: "A3", charterDocumentedAt: "2026-08-13", sponsorName: "Jordan Lee", sponsorEngagedAt: "2026-08-19",
        activities: [activity("outputs_measured", "2026-09-02"), activity("brainstorming", "2026-09-16"), activity("potential_solution", "2026-09-16", 2)],
        solutions: [solution("u1-s3", "2026-10-05", { title: "Risk-based triage", validatedAt: "2026-11-03", hours: 0.2, people: 8 })]
      }
    ]
  },
  {
    id: "user-2",
    name: "Sam Taylor",
    archetype: "Needs a starting point",
    role: "Operations",
    industry: "Banking and financial services",
    organisationSize: "Medium",
    profile: "Has noticed problems but needs structure and sponsor support to begin improving them.",
    projects: [
      { id: "u2-p1", title: "Clarify daily work priorities", summary: "Priority changes make it difficult to begin the most useful task.", status: "Draft", identifiedAt: "2026-08-05", charterType: null, charterDocumentedAt: null, sponsorName: null, sponsorEngagedAt: null, activities: [], solutions: [] },
      { id: "u2-p2", title: "Reduce unresolved inbox items", summary: "Older queries remain open without a clear next owner.", status: "Draft", identifiedAt: "2026-10-12", charterType: null, charterDocumentedAt: null, sponsorName: null, sponsorEngagedAt: null, activities: [], solutions: [] }
    ]
  },
  {
    id: "user-3",
    name: "Riley Chen",
    archetype: "Ideas awaiting delivery",
    role: "Operations",
    industry: "Banking and financial services",
    organisationSize: "Medium",
    profile: "Finds and measures problems well, but needs help converting analysis into implemented solutions.",
    projects: [
      {
        id: "u3-p1", title: "Simplify customer verification", summary: "The same information is checked at several points.", status: "Active",
        identifiedAt: "2026-02-08", charterType: "A3", charterDocumentedAt: "2026-02-18", sponsorName: "Morgan Diaz", sponsorEngagedAt: "2026-02-25",
        activities: [activity("sipoc", "2026-03-05"), activity("process_map", "2026-03-18"), activity("outputs_measured", "2026-04-06"), activity("failure_analysis", "2026-04-20")], solutions: []
      },
      {
        id: "u3-p2", title: "Improve team knowledge handover", summary: "Useful knowledge is lost between shifts.", status: "Active",
        identifiedAt: "2026-05-10", charterType: "Charter", charterDocumentedAt: "2026-05-19", sponsorName: "Morgan Diaz", sponsorEngagedAt: "2026-05-27",
        activities: [activity("process_map", "2026-06-07"), activity("brainstorming", "2026-06-22"), activity("potential_solution", "2026-06-22", 2)], solutions: []
      },
      {
        id: "u3-p3", title: "Reduce manual status updates", summary: "Colleagues recreate status information in several places.", status: "Active",
        identifiedAt: "2026-08-02", charterType: "A3", charterDocumentedAt: "2026-08-12", sponsorName: "Morgan Diaz", sponsorEngagedAt: "2026-08-20",
        activities: [activity("sipoc", "2026-09-01"), activity("outputs_measured", "2026-09-15"), activity("potential_solution", "2026-09-29", 1)],
        solutions: [solution("u3-s1", "2026-10-19", { title: "Shared daily status view", hours: 0.15, people: 5 })]
      }
    ]
  }
];

