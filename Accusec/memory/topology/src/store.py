from accusec.shared.domain.models import TopologyEdge


class TopologyStore:
    def __init__(self) -> None:
        self._edges: list[TopologyEdge] = []

    def add(self, edge: TopologyEdge) -> None:
        self._edges.append(edge)

    def for_entities(self, entity_ids: set[str]) -> list[TopologyEdge]:
        return [
            e
            for e in self._edges
            if e.source_entity_id in entity_ids or e.target_entity_id in entity_ids
        ]
