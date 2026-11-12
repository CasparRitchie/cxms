"""Presentation content for the preliminary Dash product area.

Keeping the model here, rather than in the template, gives us a clean place to
replace provisional copy with configuration or persisted organisation data later.
"""

PURPOSES = (
    {"name": "Sales", "summary": "Improve how opportunities become lasting customer value."},
    {"name": "Operations", "summary": "Make everyday work simpler, more reliable and measurable."},
    {"name": "Risk & compliance", "summary": "Turn controls and learning into practical improvements."},
    {"name": "Support", "summary": "Resolve recurring problems and improve the service experience."},
    {"name": "Fulfilment", "summary": "Improve the flow from commitment through to delivery."},
)

IMPROVEMENT_LOOP = (
    {"step": "01", "name": "Purpose", "summary": "Agree the outcome that matters and who it matters to."},
    {"step": "02", "name": "Measure", "summary": "Create a useful baseline using a small number of meaningful measures."},
    {"step": "03", "name": "Understand", "summary": "Capture observations and explore causes with the people doing the work."},
    {"step": "04", "name": "Improve", "summary": "Choose actions, assign ownership and test changes in practice."},
    {"step": "05", "name": "Learn", "summary": "Review the evidence, retain what works and begin the next cycle."},
)

WORK_AREAS = (
    {
        "label": "For employees",
        "title": "My improvements",
        "summary": "Record an opportunity, follow a guided improvement process and see whether a change worked.",
        "status": "Foundation planned",
    },
    {
        "label": "For managers",
        "title": "Team view",
        "summary": "See active work, emerging themes, measures and where teams need support.",
        "status": "Foundation planned",
    },
    {
        "label": "For programme leads",
        "title": "Improvement portfolio",
        "summary": "Connect local activity to organisational priorities and value delivered.",
        "status": "Concept stage",
    },
)

JOURNEY_STAGES = ("Learn", "Buy", "Get", "Use", "Problem", "Service", "Exit")
