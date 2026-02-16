import os
import numpy as np
from .base import EngineResult

class Neo4jEngine:
    """
    Neo4j vector index wrapper.
    Requires env vars:
      - NEO4J_URI (e.g. bolt://localhost:7687)
      - NEO4J_USER
      - NEO4J_PASSWORD
    Assumes Neo4j supports vector indexing and you create an index on :Doc(vector).
    """
    name = "neo4j"

    def __init__(self, dim: int):
        self.dim = dim
        self.uri = os.getenv("NEO4J_URI","")
        self.user = os.getenv("NEO4J_USER","")
        self.password = os.getenv("NEO4J_PASSWORD","")
        if not (self.uri and self.user and self.password):
            raise RuntimeError("Missing Neo4j env vars: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        self._driver = None

    def build(self, docs: np.ndarray) -> None:
        try:
            from neo4j import GraphDatabase
        except Exception as e:
            raise ImportError("neo4j driver not installed. Install with: pip install neo4j") from e
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        docs = np.asarray(docs, dtype=np.float32)
        with self._driver.session() as s:
            s.run("MATCH (n:Doc) DETACH DELETE n")
            # Create nodes
            batch=[]
            for i, v in enumerate(docs):
                batch.append({"id": int(i), "vector": v.tolist()})
                if len(batch)>=500:
                    s.run("UNWIND $rows AS r CREATE (:Doc {id:r.id, vector:r.vector})", rows=batch)
                    batch=[]
            if batch:
                s.run("UNWIND $rows AS r CREATE (:Doc {id:r.id, vector:r.vector})", rows=batch)
            # Create vector index if not exists (syntax varies by Neo4j version)
            s.run("CREATE VECTOR INDEX doc_vector_index IF NOT EXISTS FOR (d:Doc) ON (d.vector) OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}}", dim=self.dim)

    def search(self, queries: np.ndarray, k: int) -> EngineResult:
        if self._driver is None:
            raise RuntimeError("Driver not initialized. Did build() run?")
        queries = np.asarray(queries, dtype=np.float32)
        ids = np.full((queries.shape[0], k), -1, dtype=np.int64)
        with self._driver.session() as s:
            for i, q in enumerate(queries):
                res = s.run(
                    "CALL db.index.vector.queryNodes('doc_vector_index', $k, $q) YIELD node, score RETURN node.id AS id ORDER BY score DESC LIMIT $k",
                    k=int(k), q=q.tolist()
                )
                row=[int(r["id"]) for r in res]
                row = row[:k] + [-1]*(k-len(row))
                ids[i]=np.array(row,dtype=np.int64)
        return EngineResult(ids=ids)
