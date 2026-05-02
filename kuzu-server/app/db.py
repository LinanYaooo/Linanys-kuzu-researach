import kuzu
import threading
from queue import Queue


class KuzuDatabase:
    def __init__(self, db_path: str, buffer_pool_size: int = 0, pool_size: int = 8):
        self.db_path = db_path
        self._db = kuzu.Database(db_path, buffer_pool_size=buffer_pool_size)
        self._lock = threading.Lock()
        self._pool: Queue[kuzu.Connection] = Queue(maxsize=pool_size)
        for _ in range(pool_size):
            self._pool.put(kuzu.Connection(self._db))

    @property
    def db(self) -> kuzu.Database:
        return self._db

    def _get_conn(self) -> kuzu.Connection:
        return self._pool.get()

    def _put_conn(self, conn: kuzu.Connection):
        self._pool.put(conn)

    def execute(self, query: str) -> kuzu.QueryResult:
        conn = self._get_conn()
        try:
            return conn.execute(query)
        finally:
            self._put_conn(conn)

    def execute_safe(self, query: str) -> kuzu.QueryResult:
        with self._lock:
            conn = self._get_conn()
            try:
                return conn.execute(query)
            finally:
                self._put_conn(conn)

    def get_node_tables(self) -> list[dict]:
        result = self.execute("CALL show_tables() RETURN *")
        tables = []
        while result.has_next():
            row = result.get_next()
            if row[2] == "NODE":
                tables.append({"name": row[1], "type": row[2]})
        return tables

    def get_rel_tables(self) -> list[dict]:
        result = self.execute("CALL show_tables() RETURN *")
        tables = []
        while result.has_next():
            row = result.get_next()
            if row[2] == "REL":
                tables.append({"name": row[1], "type": row[2]})
        return tables

    def get_node_count(self) -> int:
        result = self.execute("MATCH (n) RETURN count(n)")
        return result.get_next()[0]

    def get_edge_count(self) -> int:
        result = self.execute("MATCH ()-[e]->() RETURN count(e)")
        return result.get_next()[0]

    def result_to_dicts(self, result: kuzu.QueryResult | list) -> list[dict]:
        if isinstance(result, list):
            rows = []
            for r in result:
                rows.extend(self.result_to_dicts(r))
            return rows
        columns = result.get_column_names()
        rows = []
        while result.has_next():
            row = result.get_next()
            rows.append(dict(zip(columns, row)))
        return rows

    def result_to_graph(self, result: kuzu.QueryResult) -> dict:
        columns = result.get_column_names()
        types = result.get_column_data_types()
        nodes_map: dict[str, dict] = {}
        edges_list: list[dict] = []

        def _node_key(internal_id: dict) -> str:
            return f"{internal_id['table']}_{internal_id['offset']}"

        while result.has_next():
            row = result.get_next()
            for i, val in enumerate(row):
                if not isinstance(val, dict):
                    continue
                col_type = types[i]
                if col_type == "NODE":
                    internal_id = val.get("_id", {})
                    node_key = _node_key(internal_id) if isinstance(internal_id, dict) and "table" in internal_id else str(id(val))
                    if node_key not in nodes_map:
                        label = val.get("_label", "Node")
                        props = {k: v for k, v in val.items() if k not in ("_id", "_label")}
                        display = str(props.get("name", props.get("id", label)))
                        nodes_map[node_key] = {
                            "id": node_key,
                            "label": display,
                            "group": label,
                            "properties": props,
                        }
                elif col_type == "REL":
                    src_id = val.get("_src", {})
                    dst_id = val.get("_dst", {})
                    src_key = _node_key(src_id) if isinstance(src_id, dict) and "table" in src_id else f"src_{len(edges_list)}"
                    dst_key = _node_key(dst_id) if isinstance(dst_id, dict) and "table" in dst_id else f"dst_{len(edges_list)}"
                    rel_label = val.get("_label", "REL")
                    props = {k: v for k, v in val.items() if k not in ("_id", "_label", "_src", "_dst")}
                    edges_list.append({
                        "from_": src_key,
                        "to": dst_key,
                        "label": rel_label,
                        "properties": props,
                    })

        return {
            "nodes": list(nodes_map.values()),
            "edges": edges_list,
        }


_db_instance: KuzuDatabase | None = None


def init_db(db_path: str, buffer_pool_size: int = 0, pool_size: int = 8) -> KuzuDatabase:
    global _db_instance
    _db_instance = KuzuDatabase(db_path, buffer_pool_size, pool_size)
    return _db_instance


def get_db() -> KuzuDatabase:
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_instance
