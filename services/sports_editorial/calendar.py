class RepositoryCalendarProvider:
    """Calendar catalogue boundary; replace with FIS API/export sync when supplied."""

    provider_name = "local_catalogue"

    def __init__(self, repository):
        self.repository = repository

    def list_events(self):
        return [
            entity for entity in self.repository.list_entities()
            if entity.get("entity_type") == "event"
            and str(entity.get("canonical_id") or "").isdigit()
        ]
