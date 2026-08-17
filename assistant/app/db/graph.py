"""Kuzu embedded graph wrapper. Ported from the narrative engine's
db/graph.py — same API shape and same caveats (parameter-binding call shape
not re-verified against a live install this session; delete-then-insert used
in place of an unconfirmed upsert/MERGE). See that project's graph.py
docstring for the full note.

Schema retargeted: Character -> Person, Beat -> Commitment, RelatesTo
unchanged, ObligatedTo -> Concerns (reversed direction/meaning — a commitment
*concerns* a person, rather than a character being obligated to a beat; see
DESIGN.md §2 for why the relationship inverts here).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import kuzu


class AssistantGraph:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = kuzu.Database(db_path)
        self.conn = kuzu.Connection(self.db)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        statements = [
            "CREATE NODE TABLE Person(id STRING, name STRING, PRIMARY KEY (id))",
            "CREATE NODE TABLE Commitment(id STRING, description STRING, status STRING, PRIMARY KEY (id))",
            "CREATE REL TABLE RelatesTo(FROM Person TO Person, "
            "relation_type STRING, polarity DOUBLE, valid_from_turn INT64)",
            "CREATE REL TABLE Concerns(FROM Commitment TO Person, note STRING)",
        ]
        for stmt in statements:
            try:
                self.conn.execute(stmt)
            except RuntimeError:
                pass  # table already exists — see module docstring

    def upsert_person(self, person_id: str, name: str) -> None:
        self.conn.execute("MATCH (p:Person {id: $id}) DELETE p", parameters={"id": person_id})
        self.conn.execute("CREATE (p:Person {id: $id, name: $name})", parameters={"id": person_id, "name": name})

    def upsert_commitment(self, commitment_id: str, description: str, status: str) -> None:
        self.conn.execute("MATCH (c:Commitment {id: $id}) DELETE c", parameters={"id": commitment_id})
        self.conn.execute(
            "CREATE (c:Commitment {id: $id, description: $description, status: $status})",
            parameters={"id": commitment_id, "description": description, "status": status},
        )

    def upsert_relationship(
        self, party_a: str, party_b: str, relation_type: str, polarity: float, valid_from_turn: int
    ) -> None:
        self.conn.execute(
            "MATCH (a:Person {id: $a})-[r:RelatesTo]->(b:Person {id: $b}) DELETE r",
            parameters={"a": party_a, "b": party_b},
        )
        self.conn.execute(
            """
            MATCH (a:Person {id: $a}), (b:Person {id: $b})
            CREATE (a)-[:RelatesTo {relation_type: $rtype, polarity: $polarity, valid_from_turn: $turn}]->(b)
            """,
            parameters={"a": party_a, "b": party_b, "rtype": relation_type, "polarity": polarity, "turn": valid_from_turn},
        )

    def upsert_concern(self, commitment_id: str, person_id: str, note: str = "") -> None:
        self.conn.execute(
            "MATCH (c:Commitment {id: $cid})-[r:Concerns]->(p:Person {id: $pid}) DELETE r",
            parameters={"cid": commitment_id, "pid": person_id},
        )
        self.conn.execute(
            """
            MATCH (c:Commitment {id: $cid}), (p:Person {id: $pid})
            CREATE (c)-[:Concerns {note: $note}]->(p)
            """,
            parameters={"cid": commitment_id, "pid": person_id, "note": note},
        )

    def one_hop_relationships(self, person_id: str) -> list[dict[str, Any]]:
        result = self.conn.execute(
            """
            MATCH (a:Person {id: $id})-[r:RelatesTo]->(b:Person)
            RETURN b.id AS other_id, b.name AS other_name, r.relation_type AS relation_type,
                   r.polarity AS polarity, r.valid_from_turn AS valid_from_turn
            """,
            parameters={"id": person_id},
        )
        rows = []
        while result.has_next():
            row = result.get_next()
            rows.append(
                {
                    "other_id": row[0],
                    "other_name": row[1],
                    "relation_type": row[2],
                    "polarity": row[3],
                    "valid_from_turn": row[4],
                }
            )
        return rows

    def commitments_concerning(self, person_id: str) -> list[dict[str, Any]]:
        result = self.conn.execute(
            """
            MATCH (c:Commitment)-[r:Concerns]->(p:Person {id: $id})
            RETURN c.id AS commitment_id, c.description AS description, c.status AS status, r.note AS note
            """,
            parameters={"id": person_id},
        )
        rows = []
        while result.has_next():
            row = result.get_next()
            rows.append({"commitment_id": row[0], "description": row[1], "status": row[2], "note": row[3]})
        return rows


_graph: AssistantGraph | None = None


def init_graph(db_path: str) -> AssistantGraph:
    global _graph
    if _graph is None:
        _graph = AssistantGraph(db_path)
    return _graph


def get_graph() -> AssistantGraph:
    if _graph is None:
        raise RuntimeError("Graph not initialized — call init_graph() at startup")
    return _graph
