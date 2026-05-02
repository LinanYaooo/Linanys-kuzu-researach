from __future__ import annotations

import csv
import io
import sys
import threading
import time
from enum import Enum
from queue import Queue
from typing import Any, Iterator
from urllib.parse import quote_plus

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------------------
# Source config
# ---------------------------------------------------------------------------

class SourceDBType(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class SourceConfig(BaseModel):
    db_type: SourceDBType
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    database: str

    def dsn(self) -> str:
        if self.db_type == SourceDBType.SQLITE:
            return f"sqlite:///{self.database}"
        user = quote_plus(self.username or "")
        pwd = quote_plus(self.password or "")
        if self.db_type == SourceDBType.POSTGRESQL:
            port = self.port or 5432
            return f"postgresql+psycopg2://{user}:{pwd}@{self.host}:{port}/{self.database}"
        if self.db_type == SourceDBType.MYSQL:
            port = self.port or 3306
            return f"mysql+pymysql://{user}:{pwd}@{self.host}:{port}/{self.database}"
        raise ValueError(f"Unsupported db_type: {self.db_type}")


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

class FieldMapping(BaseModel):
    source_field: str
    target_property: str
    transform: str | None = None


# ---------------------------------------------------------------------------
# Incremental config
# ---------------------------------------------------------------------------

class IncrementalConfig(BaseModel):
    enabled: bool = False
    where_fragment: str = ""
    watermark_field: str | None = None
    watermark_value: str | None = None


# ---------------------------------------------------------------------------
# Target config
# ---------------------------------------------------------------------------

class TargetConfig(BaseModel):
    server_url: str = "http://127.0.0.1:8000/api/v1"
    entity_name: str
    is_rel: bool = False
    rel_from: str | None = None
    rel_to: str | None = None


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------

class RunResult(BaseModel):
    extracted: int = 0
    written: int = 0
    elapsed_ms: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------

def _create_engine(source: SourceConfig) -> Engine:
    return create_engine(source.dsn(), pool_pre_ping=True)


def _get_table_columns(engine: Engine, table: str, schema: str | None = None) -> list[str]:
    insp = inspect(engine)
    return [c["name"] for c in insp.get_columns(table, schema=schema)]


def _get_table_columns_with_types(engine: Engine, table: str, schema: str | None = None) -> list[dict[str, str]]:
    insp = inspect(engine)
    return [{"name": c["name"], "type": str(c["type"])} for c in insp.get_columns(table, schema=schema)]


_SQL_TO_KUZU = {
    "INTEGER": "INT64", "BIGINT": "INT64", "SMALLINT": "INT64", "INT": "INT64",
    "FLOAT": "DOUBLE", "DOUBLE": "DOUBLE", "REAL": "DOUBLE", "NUMERIC": "DOUBLE",
    "BOOLEAN": "BOOL", "BOOL": "BOOL",
    "TIMESTAMP": "STRING", "DATE": "STRING", "TIME": "STRING",
    "JSON": "STRING", "JSONB": "STRING",
    "UUID": "STRING",
}


def _map_kuzu_type(sql_type: str) -> str:
    upper = sql_type.upper()
    if upper.startswith("VARCHAR") or upper.startswith("CHAR") or upper.startswith("TEXT"):
        return "STRING"
    for prefix, kuzu in _SQL_TO_KUZU.items():
        if upper.startswith(prefix):
            return kuzu
    return "STRING"


def _ensure_table(config: TargetConfig, columns: list[dict[str, str]], primary_key: str | None = None) -> None:
    url = config.server_url.rstrip("/") + "/schema/nodes"
    resp = httpx.get(url, timeout=30.0)
    if resp.status_code == 200:
        names = [t["name"] for t in resp.json()]
        if config.entity_name in names:
            return

    if config.is_rel:
        props = ", ".join(f'{c["name"]} {_map_kuzu_type(c["type"])}' for c in columns)
        ddl = f'CREATE REL TABLE {config.entity_name} (FROM {config.rel_from} TO {config.rel_to}, {props})'
    else:
        prop_defs = [f'{c["name"]} {_map_kuzu_type(c["type"])}' for c in columns]
        pk = primary_key or columns[0]["name"]
        ddl = f"CREATE NODE TABLE {config.entity_name} ({', '.join(prop_defs)}, PRIMARY KEY ({pk}))"

    query_url = config.server_url.rstrip("/") + "/query/safe"
    resp = httpx.post(query_url, json={"query": ddl}, timeout=30.0)
    if resp.status_code != 200:
        detail = resp.text
        try:
            body = resp.json()
            detail = body.get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(f"Kuzu auto-create failed {resp.status_code}: {detail}")


def _build_sql(
    table: str,
    fields: list[str] | None = None,
    schema: str | None = None,
    where: str = "",
    custom_query: str | None = None,
) -> str:
    if custom_query:
        sql = custom_query
        if where:
            if "where" in sql.lower():
                sql = f"{sql} AND ({where})"
            else:
                sql = f"{sql} WHERE {where}"
        return sql
    qualified = f"{schema}.{table}" if schema else table
    cols = ", ".join(fields) if fields else "*"
    sql = f"SELECT {cols} FROM {qualified}"
    if where:
        sql = f"{sql} WHERE {where}"
    return sql


def _extract(engine: Engine, sql: str, batch_size: int = 1000) -> Iterator[list[dict[str, Any]]]:
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(text(sql))
        batch: list[dict[str, Any]] = []
        for row in result.mappings():
            batch.append(dict(row))
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch


# ---------------------------------------------------------------------------
# Target helpers
# ---------------------------------------------------------------------------

def _escape(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    return "'" + str(value).replace("'", "\\'") + "'"


def _apply_transform(value: Any, transform: str | None) -> Any:
    if not transform:
        return value
    return eval(transform, {"__builtins__": {}}, {"value": value, "str": str, "int": int, "float": float, "bool": bool})


def _build_node_cypher(entity: str, row: dict, mappings: list[FieldMapping]) -> str:
    props = []
    for m in mappings:
        val = _apply_transform(row.get(m.source_field), m.transform)
        props.append(f"{m.target_property}: {_escape(val)}")
    return f"CREATE (:{entity} {{{', '.join(props)}}})"


def _build_rel_cypher(rel: str, from_ent: str, to_ent: str, row: dict, mappings: list[FieldMapping]) -> str:
    from_key = to_key = None
    props = []
    for m in mappings:
        val = _apply_transform(row.get(m.source_field), m.transform)
        if m.target_property == "_from_id":
            from_key = _escape(val)
        elif m.target_property == "_to_id":
            to_key = _escape(val)
        else:
            props.append(f"{m.target_property}: {_escape(val)}")
    return (
        f"MATCH (a:{from_ent} {{id: {from_key}}}), "
        f"(b:{to_ent} {{id: {to_key}}}) "
        f"CREATE (a)-[:{rel} {{{', '.join(props)}}}]->(b)"
    )


def _rows_to_csv(rows: list[dict], mappings: list[FieldMapping]) -> str:
    fieldnames = [m.target_property for m in mappings]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        out = {}
        for m in mappings:
            val = _apply_transform(row.get(m.source_field), m.transform)
            out[m.target_property] = val
        writer.writerow(out)
    return buf.getvalue()


def _write_batch(config: TargetConfig, mappings: list[FieldMapping], rows: list[dict], chunk_size: int = 50, client: httpx.Client | None = None) -> int:
    if not rows:
        return 0
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=120.0)
    try:
        url = config.server_url.rstrip("/") + f"/import/{config.entity_name}"
        written = 0
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            csv_data = _rows_to_csv(chunk, mappings)
            resp = client.post(url, content=csv_data.encode("utf-8"), headers={"Content-Type": "text/csv"})
            if resp.status_code != 200:
                detail = resp.text
                try:
                    body = resp.json()
                    detail = body.get("detail", detail)
                except Exception:
                    pass
                raise RuntimeError(f"Kuzu bulk import {resp.status_code}: {detail}")
            written += len(chunk)
    finally:
        if own_client:
            client.close()
    return written


# ---------------------------------------------------------------------------
# Incremental helpers
# ---------------------------------------------------------------------------

def _resolve_where(incremental: IncrementalConfig) -> str:
    if not incremental.enabled or not incremental.where_fragment:
        return ""
    fragment = incremental.where_fragment
    if incremental.watermark_field and incremental.watermark_value is not None:
        if "${watermark}" in fragment:
            return fragment.replace("${watermark}", incremental.watermark_value)
        return f"{fragment} AND {incremental.watermark_field} > '{incremental.watermark_value}'" if fragment else f"{incremental.watermark_field} > '{incremental.watermark_value}'"
    return fragment


def _update_watermark(batch: list[dict], incremental: IncrementalConfig) -> None:
    field = incremental.watermark_field
    if not field:
        return
    max_val = None
    for row in batch:
        v = row.get(field)
        if v is not None and (max_val is None or str(v) > str(max_val)):
            max_val = v
    if max_val is not None:
        incremental.watermark_value = str(max_val)


def _progress_bar(entity: str, current: int, total: int, elapsed_ms: float, width: int = 30) -> None:
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = current / total * 100 if total else 0
    line = f"\r  {entity} |{bar}| {pct:5.1f}% {current}/{total} {elapsed_ms/1000:.1f}s"
    sys.stderr.write(line)
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# ETLTask
# ---------------------------------------------------------------------------

class ETLTask:
    """ETL 抽取任务。用户通过编程式定义源端、映射、目标和增量配置，调用 run() 执行。

    用法::

        from kuzu_etl import ETLTask

        task = ETLTask(
            source_db="postgresql",
            source_host="localhost",
            source_database="mydb",
            source_username="postgres",
            source_password="your_password",
            source_table="account",
            fields=[
                {"source_field": "id", "target_property": "id"},
                {"source_field": "name", "target_property": "name"},
            ],
            target_entity="Account",
        )
        result = task.run()
        print(result)
    """

    def __init__(
        self,
        # source
        source_db: str = "sqlite",
        source_host: str | None = None,
        source_port: int | None = None,
        source_username: str | None = None,
        source_password: str | None = None,
        source_database: str = "",
        source_schema: str | None = None,
        source_table: str = "",
        source_query: str | None = None,
        # fields
        fields: list[dict | FieldMapping] | None = None,
        # target
        target_server: str = "http://127.0.0.1:8000/api/v1",
        target_entity: str = "",
        target_is_rel: bool = False,
        target_rel_from: str | None = None,
        target_rel_to: str | None = None,
        # incremental
        incremental: bool = False,
        where_fragment: str = "",
        watermark_field: str | None = None,
        watermark_value: str | None = None,
        # batch
        batch_size: int = 5000,
        write_chunk_size: int = 5000,
        show_progress: bool = True,
    ):
        self.source = SourceConfig(
            db_type=SourceDBType(source_db),
            host=source_host,
            port=source_port,
            username=source_username,
            password=source_password,
            database=source_database,
        )
        self.source_schema = source_schema
        self.source_table = source_table
        self.source_query = source_query

        self.fields: list[FieldMapping] = [
            f if isinstance(f, FieldMapping) else FieldMapping(**f)
            for f in (fields or [])
        ]

        self.target = TargetConfig(
            server_url=target_server,
            entity_name=target_entity,
            is_rel=target_is_rel,
            rel_from=target_rel_from,
            rel_to=target_rel_to,
        )

        self.incremental = IncrementalConfig(
            enabled=incremental,
            where_fragment=where_fragment,
            watermark_field=watermark_field,
            watermark_value=watermark_value,
        )

        self.batch_size = batch_size
        self.write_chunk_size = write_chunk_size
        self.show_progress = show_progress

    def run(self, incremental: bool | None = None) -> RunResult:
        """执行 ETL 任务。

        Args:
            incremental: 覆盖增量设置。True 强制增量，False 强制全量，None 使用构造时的配置。

        Returns:
            RunResult 包含抽取行数、写入行数、耗时和错误信息。
        """
        start = time.perf_counter()
        result = RunResult()

        try:
            inc = self.incremental.model_copy()
            if incremental is not None:
                inc.enabled = incremental

            mappings = self._resolve_mappings()
            field_names = [m.source_field for m in mappings] if mappings else None

            where = _resolve_where(inc) if inc.enabled else ""
            sql = _build_sql(
                table=self.source_table,
                fields=field_names,
                schema=self.source_schema,
                where=where,
                custom_query=self.source_query,
            )

            engine = _create_engine(self.source)

            if not self.source_query:
                cols_with_types = _get_table_columns_with_types(engine, self.source_table, self.source_schema)
                _ensure_table(self.target, cols_with_types)

            # Get total count for progress bar
            total = 0
            if self.show_progress:
                count_sql = f"SELECT count(*) FROM {f'{self.source_schema}.{self.source_table}' if self.source_schema else self.source_table}"
                if where:
                    count_sql += f" WHERE {where}"
                with engine.connect() as conn:
                    total = conn.execute(text(count_sql)).scalar() or 0

            # Pipeline: extract and write in parallel
            queue: Queue[list[dict] | None] = Queue(maxsize=4)
            write_error: list[str] = []
            active_writers = 0
            writers_done = threading.Event()
            lock = threading.Lock()

            num_writers = 4

            def _writer():
                nonlocal active_writers
                client = httpx.Client(timeout=120.0)
                try:
                    while True:
                        batch = queue.get()
                        if batch is None:
                            queue.put(None)
                            with lock:
                                active_writers -= 1
                                if active_writers == 0:
                                    writers_done.set()
                            break
                        n = _write_batch(self.target, mappings, batch, self.write_chunk_size, client)
                        with lock:
                            result.written += n
                        if inc.enabled:
                            _update_watermark(batch, inc)
                            self.incremental.watermark_value = inc.watermark_value
                        if self.show_progress:
                            _progress_bar(self.target.entity_name, result.written, total, (time.perf_counter() - start) * 1000)
                except Exception as e:
                    write_error.append(str(e))
                finally:
                    client.close()

            with lock:
                active_writers = num_writers
            writer_threads = [threading.Thread(target=_writer, daemon=True) for _ in range(num_writers)]
            for t in writer_threads:
                t.start()

            for batch in _extract(engine, sql, self.batch_size):
                result.extracted += len(batch)
                queue.put(batch)

            for _ in range(num_writers):
                queue.put(None)

            writers_done.wait(timeout=300)

            if self.show_progress:
                _progress_bar(self.target.entity_name, result.written, total, (time.perf_counter() - start) * 1000)
                sys.stderr.write("\n")

            if write_error:
                raise RuntimeError(write_error[0])

        except Exception as e:
            result.error = str(e)

        result.elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return result

    def _resolve_mappings(self) -> list[FieldMapping]:
        if self.fields:
            return self.fields
        if self.source_query:
            return []
        engine = _create_engine(self.source)
        cols = _get_table_columns(engine, self.source_table, self.source_schema)
        return [FieldMapping(source_field=c, target_property=c) for c in cols]

    def count(self) -> int:
        """查询目标库中同名节点的数量。"""
        url = self.target.server_url.rstrip("/") + "/query"
        query = f"MATCH (n:{self.target.entity_name}) RETURN count(n) AS cnt"
        resp = httpx.post(url, json={"query": query}, timeout=30.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Kuzu count failed: {resp.text}")
        rows = resp.json().get("results", [])
        return rows[0]["cnt"] if rows else 0

    def clear(self) -> int:
        """删除目标库中同名节点的全部数据，返回删除的数量。"""
        deleted = self.count()
        url = self.target.server_url.rstrip("/") + "/query/safe"
        query = f"MATCH (n:{self.target.entity_name}) DELETE n"
        resp = httpx.post(url, json={"query": query}, timeout=120.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Kuzu clear failed: {resp.text}")
        return deleted
