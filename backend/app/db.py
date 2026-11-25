"""Local Postgres access (psycopg 3) with the query surface the JobPilot code uses.

The ported code was written against supabase-py's PostgREST builder
(``db.table(t).select(...).eq(...).execute().data`` and ``db.rpc(name, params)``).
This module keeps that surface so the code runs unchanged on local Postgres, and
mirrors PostgREST where it matters:

* rows come back as ``to_jsonb(row)``, so uuids, timestamps and numerics have the
  same JSON shapes PostgREST returned;
* every value is cast to its column's real type (read from the catalog);
* RPCs are called with named, typed arguments; ``void`` returns ``None``;
* each ``execute()`` is one transaction. ``get_db(user_id)`` sets the transaction
  setting ``app.user_id``, which ``auth.uid()`` reads (see migrations/0001).

Unsupported builder features raise ``DatabaseError`` instead of guessing.
Unfiltered update/delete are refused.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from app.config import settings

PAGE_SIZE = 1000  # page size for select_all
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_JSON_PATH = re.compile(r"^([a-z_][a-z0-9_]*)->>([a-z_][a-z0-9_]*)$")


class DatabaseError(Exception):
    """A database or query-building error. ``code`` is the SQLSTATE, like PostgREST's APIError."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class Result:
    data: Any
    count: int | None = None


# --- connection pool --------------------------------------------------------------------------

_pool = None
_pool_lock = threading.Lock()


def _conninfo() -> str:
    url = settings.DATABASE_URL.strip()
    if not url:
        raise DatabaseError("DATABASE_URL is not set. Start the local stack (see README, Local stack).")
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", url)


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool
            _pool = ConnectionPool(_conninfo(), min_size=1, max_size=settings.DATABASE_POOL_SIZE,
                                   check=ConnectionPool.check_connection, open=True,
                                   kwargs={"connect_timeout": 10})
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


# --- catalog cache ----------------------------------------------------------------------------

@dataclass(frozen=True)
class _Table:
    columns: dict[str, str]  # name -> format_type, e.g. "uuid", "text[]", "jsonb"
    primary_key: tuple[str, ...]


@dataclass(frozen=True)
class _Function:
    args: dict[str, str]  # argument name -> type
    returns: str


_tables: dict[str, _Table] = {}
_functions: dict[str, _Function] = {}
_catalog_lock = threading.Lock()


def _table_info(conn, name: str) -> _Table:
    with _catalog_lock:
        if name in _tables:
            return _tables[name]
    rows = conn.execute(
        """select a.attname, format_type(a.atttypid, a.atttypmod),
                  coalesce(a.attnum = any(i.indkey), false)
           from pg_attribute a
           left join pg_index i on i.indrelid = a.attrelid and i.indisprimary
           where a.attrelid = to_regclass(%s) and a.attnum > 0 and not a.attisdropped
           order by a.attnum""",
        ["public." + name],
    ).fetchall()
    if not rows:
        raise DatabaseError(f'relation "public.{name}" does not exist', "42P01")
    info = _Table({r[0]: r[1] for r in rows}, tuple(r[0] for r in rows if r[2]))
    with _catalog_lock:
        _tables[name] = info
    return info


def _function_info(conn, name: str) -> _Function:
    with _catalog_lock:
        if name in _functions:
            return _functions[name]
    rows = conn.execute(
        """select coalesce(p.proargnames, '{}'),
                  array(select format_type(t, null) from unnest(p.proargtypes) t),
                  format_type(p.prorettype, null)
           from pg_proc p where p.pronamespace = 'public'::regnamespace and p.proname = %s""",
        [name],
    ).fetchall()
    if len(rows) != 1:
        raise DatabaseError(f"function public.{name} does not exist or is overloaded", "42883")
    names, types, returns = rows[0]
    info = _Function(dict(zip(names, types)), returns)
    with _catalog_lock:
        _functions[name] = info
    return info


def clear_catalog_cache() -> None:
    """Forget cached table/function shapes (call after migrations in a long-lived process)."""
    with _catalog_lock:
        _tables.clear()
        _functions.clear()


def _adapt(value: Any, column_type: str) -> Any:
    if value is None:
        return None
    if column_type in ("json", "jsonb") or isinstance(value, dict):
        return Jsonb(value)
    return value


def _cast(column_type: str) -> sql.Composable:
    # column_type comes from the catalog (format_type), never from callers.
    return sql.SQL("%s::" + column_type)


# --- execution --------------------------------------------------------------------------------

class Database:
    """One logical client. Cheap to create; connections come from a shared pool."""

    def __init__(self, user_id: str | None = None):
        self.user_id = str(user_id) if user_id else None

    def table(self, name: str) -> "Query":
        if not _IDENT.match(name):
            raise DatabaseError(f"invalid table name: {name!r}")
        return Query(self, name)

    def rpc(self, name: str, params: dict | None = None) -> "Rpc":
        if not _IDENT.match(name):
            raise DatabaseError(f"invalid function name: {name!r}")
        return Rpc(self, name, dict(params or {}))

    def fetch(self, query: str, params: Any = None) -> list[tuple]:
        """Run raw SQL (trusted, static text with %s placeholders) and return rows."""
        return self._run(lambda conn: _rows(conn.execute(query, params)))

    def run(self, work):
        """Run ``work(conn)`` in one transaction (with app.user_id set) and return its result.

        For multi-statement logic that must be atomic (the action state machine, imports)."""
        return self._run(work)

    def _run(self, work):
        try:
            with _get_pool().connection() as conn:
                with conn.transaction():
                    if self.user_id:
                        conn.execute("select set_config('app.user_id', %s, true)", [self.user_id])
                    return work(conn)
        except psycopg.Error as exc:
            message = (exc.diag.message_primary if exc.diag else None) or str(exc)
            raise DatabaseError(message, exc.sqlstate) from exc


def _rows(cursor) -> list[tuple]:
    return cursor.fetchall() if cursor.description else []


def get_db(user_id: str | None = None) -> Database:
    """Database client. Pass the signed-in owner's id so auth.uid() and column defaults see it."""
    return Database(user_id)


class Rpc:
    def __init__(self, db: Database, name: str, params: dict):
        self.db, self.name, self.params = db, name, params

    def execute(self) -> Result:
        def work(conn):
            fn = _function_info(conn, self.name)
            unknown = set(self.params) - set(fn.args)
            if unknown:
                raise DatabaseError(f"function public.{self.name} has no argument(s) {sorted(unknown)}", "42883")
            args = [sql.SQL("{} => ").format(sql.Identifier(k)) + _cast(fn.args[k]) for k in self.params]
            call = sql.SQL("public.{}({})").format(sql.Identifier(self.name), sql.SQL(", ").join(args))
            values = [_adapt(v, fn.args[k]) for k, v in self.params.items()]
            if fn.returns == "void":
                conn.execute(sql.SQL("select {}").format(call), values)
                return Result(None)
            row = conn.execute(sql.SQL("select to_jsonb({})").format(call), values).fetchone()
            return Result(row[0] if row else None)

        return self.db._run(work)


class Query:
    """A small, strict subset of postgrest-py's request builder."""

    def __init__(self, db: Database, table: str):
        self.db, self.table = db, table
        self._op: str | None = None
        self._columns: list[str] | None = None
        self._count: str | None = None
        self._payload: Any = None
        self._on_conflict: list[str] | None = None
        self._ignore_duplicates = False
        self._filters: list[tuple[str, str, Any]] = []
        self._order: list[tuple[str, bool, bool | None]] = []
        self._limit: int | None = None
        self._offset: int | None = None

    # operations
    def select(self, columns: str = "*", *, count: str | None = None) -> "Query":
        self._set_op("select")
        cols = [c.strip() for c in columns.split(",") if c.strip()]
        if cols != ["*"]:
            for c in cols:
                if not _IDENT.match(c):
                    raise DatabaseError(f"unsupported select column {c!r} (plain column names or * only)")
        self._columns = None if cols == ["*"] else cols
        if count not in (None, "exact"):
            raise DatabaseError(f"unsupported count mode {count!r}")
        self._count = count
        return self

    def insert(self, json: dict | list[dict], *, count: str | None = None, returning: str | None = None,
               upsert: bool = False, default_to_null: bool = True) -> "Query":
        self._set_op("upsert" if upsert else "insert")
        self._payload = json
        return self

    def upsert(self, json: dict | list[dict], *, count: str | None = None, returning: str | None = None,
               ignore_duplicates: bool = False, on_conflict: str = "", default_to_null: bool = True) -> "Query":
        self._set_op("upsert")
        self._payload = json
        self._ignore_duplicates = ignore_duplicates
        self._on_conflict = [c.strip() for c in on_conflict.split(",") if c.strip()] or None
        return self

    def update(self, json: dict, *, count: str | None = None, returning: str | None = None) -> "Query":
        self._set_op("update")
        if not isinstance(json, dict) or not json:
            raise DatabaseError("update needs a non-empty dict")
        self._payload = json
        return self

    def delete(self, *, count: str | None = None, returning: str | None = None) -> "Query":
        self._set_op("delete")
        return self

    # filters
    def eq(self, column: str, value: Any) -> "Query":
        return self._filter(column, "=", value)

    def neq(self, column: str, value: Any) -> "Query":
        return self._filter(column, "<>", value)

    def gt(self, column: str, value: Any) -> "Query":
        return self._filter(column, ">", value)

    def gte(self, column: str, value: Any) -> "Query":
        return self._filter(column, ">=", value)

    def lt(self, column: str, value: Any) -> "Query":
        return self._filter(column, "<", value)

    def lte(self, column: str, value: Any) -> "Query":
        return self._filter(column, "<=", value)

    def in_(self, column: str, values) -> "Query":
        return self._filter(column, "in", list(values))

    def is_(self, column: str, value: Any) -> "Query":
        if value not in (None, "null", True, False, "true", "false"):
            raise DatabaseError(f"is_ supports null/true/false, not {value!r}")
        return self._filter(column, "is", value)

    def match(self, query: dict) -> "Query":
        for column, value in query.items():
            self.eq(column, value)
        return self

    # modifiers
    def order(self, column: str, *, desc: bool = False, nullsfirst: bool | None = None) -> "Query":
        self._column_ref(column)
        self._order.append((column, desc, nullsfirst))
        return self

    def limit(self, size: int) -> "Query":
        self._limit = int(size)
        return self

    def range(self, start: int, end: int) -> "Query":
        self._offset, self._limit = int(start), int(end) - int(start) + 1
        return self

    def execute(self) -> Result:
        if self._op is None:
            raise DatabaseError("call select/insert/upsert/update/delete before execute()")
        return self.db._run(getattr(self, "_exec_" + self._op))

    # internals
    def _set_op(self, op: str) -> None:
        if self._op is not None:
            raise DatabaseError(f"{op}() after {self._op}() is not supported")
        self._op = op

    def _filter(self, column: str, op: str, value: Any) -> "Query":
        self._column_ref(column)
        self._filters.append((column, op, value))
        return self

    @staticmethod
    def _column_ref(column: str) -> None:
        if not (_IDENT.match(column) or _JSON_PATH.match(column)):
            raise DatabaseError(f"unsupported column reference {column!r}")

    def _column_type(self, info: _Table, column: str) -> str:
        if column not in info.columns:
            raise DatabaseError(f'column "{column}" of relation "{self.table}" does not exist', "42703")
        return info.columns[column]

    def _where(self, info: _Table) -> tuple[sql.Composable, list]:
        parts, values = [], []
        for column, op, value in self._filters:
            path = _JSON_PATH.match(column)
            if path:
                if self._column_type(info, path.group(1)) not in ("json", "jsonb"):
                    raise DatabaseError(f"{path.group(1)} is not a json column")
                ref = sql.SQL("(x.{} ->> %s)").format(sql.Identifier(path.group(1)))
                values.append(path.group(2))
                ctype = "text"
            else:
                ref = sql.SQL("x.{}").format(sql.Identifier(column))
                ctype = self._column_type(info, column)
            if op == "is":
                literal = {None: "null", "null": "null", True: "true", "true": "true", False: "false", "false": "false"}[value]
                parts.append(ref + sql.SQL(" is " + literal))
            elif value is None and op in ("=", "<>"):
                parts.append(ref + sql.SQL(" is null" if op == "=" else " is not null"))
            elif op == "in":
                parts.append(ref + sql.SQL(" = any(%s::" + ctype + "[])"))
                values.append([_adapt(v, ctype) for v in value])
            else:
                parts.append(ref + sql.SQL(f" {op} ") + _cast(ctype))
                values.append(_adapt(value, ctype))
        if not parts:
            return sql.SQL(""), values
        return sql.SQL(" where ") + sql.SQL(" and ").join(parts), values

    def _require_filters(self) -> None:
        if not self._filters:
            raise DatabaseError(f"refusing unfiltered {self._op} on {self.table}")

    def _exec_select(self, conn) -> Result:
        info = _table_info(conn, self.table)
        if self._columns:
            for c in self._columns:
                self._column_type(info, c)
            row_expr = sql.SQL("to_jsonb(s) from public.{} as x cross join lateral (select {}) as s").format(
                sql.Identifier(self.table), sql.SQL(", ").join(sql.SQL("x.{}").format(sql.Identifier(c)) for c in self._columns))
        else:
            row_expr = sql.SQL("to_jsonb(x) from public.{} as x").format(sql.Identifier(self.table))
        where, values = self._where(info)
        query = sql.SQL("select ") + row_expr + where
        if self._order:
            items = []
            for column, desc, nullsfirst in self._order:
                path = _JSON_PATH.match(column)
                ref = (sql.SQL("(x.{} ->> {})").format(sql.Identifier(path.group(1)), sql.Literal(path.group(2))) if path
                       else sql.SQL("x.{}").format(sql.Identifier(column)))
                if not path:
                    self._column_type(info, column)
                # PostgREST default: nulls last for asc, nulls first for desc (same as Postgres).
                nulls = "" if nullsfirst is None else (" nulls first" if nullsfirst else " nulls last")
                items.append(ref + sql.SQL((" desc" if desc else " asc") + nulls))
            query += sql.SQL(" order by ") + sql.SQL(", ").join(items)
        if self._limit is not None:
            query += sql.SQL(" limit {}").format(sql.Literal(self._limit))
        if self._offset:
            query += sql.SQL(" offset {}").format(sql.Literal(self._offset))
        data = [r[0] for r in conn.execute(query, values).fetchall()]
        count = None
        if self._count == "exact":
            count = conn.execute(sql.SQL("select count(*) from public.{} as x").format(sql.Identifier(self.table)) + where,
                                 values).fetchone()[0]
        return Result(data, count)

    def _rows_and_columns(self, info: _Table) -> tuple[list[dict], list[str]]:
        rows = self._payload if isinstance(self._payload, list) else [self._payload]
        if not rows or not all(isinstance(r, dict) and r for r in rows):
            raise DatabaseError(f"{self._op} needs a non-empty dict or list of dicts")
        columns: list[str] = []
        for row in rows:
            for c in row:
                if c not in columns:
                    self._column_type(info, c)
                    columns.append(c)
        return rows, columns

    def _exec_insert(self, conn) -> Result:
        return self._write_rows(conn, upsert=False)

    def _exec_upsert(self, conn) -> Result:
        return self._write_rows(conn, upsert=True)

    def _write_rows(self, conn, upsert: bool) -> Result:
        info = _table_info(conn, self.table)
        rows, columns = self._rows_and_columns(info)
        values, tuples = [], []
        for row in rows:
            cells = []
            for c in columns:
                if c in row:
                    cells.append(_cast(info.columns[c]))
                    values.append(_adapt(row[c], info.columns[c]))
                else:
                    cells.append(sql.SQL("default"))  # missing key: column default
            tuples.append(sql.SQL("(") + sql.SQL(", ").join(cells) + sql.SQL(")"))
        query = sql.SQL("insert into public.{} as x ({}) values ").format(
            sql.Identifier(self.table), sql.SQL(", ").join(map(sql.Identifier, columns))) + sql.SQL(", ").join(tuples)
        if upsert:
            target = self._on_conflict or list(info.primary_key)
            if not target:
                raise DatabaseError(f"{self.table} has no primary key; pass on_conflict")
            for c in target:
                self._column_type(info, c)
            conflict = sql.SQL(" on conflict ({})").format(sql.SQL(", ").join(map(sql.Identifier, target)))
            if self._ignore_duplicates:
                query += conflict + sql.SQL(" do nothing")
            else:
                updates = [c for c in columns if c not in target] or target
                query += conflict + sql.SQL(" do update set ") + sql.SQL(", ").join(
                    sql.SQL("{} = excluded.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in updates)
        query += sql.SQL(" returning to_jsonb(x)")
        return Result([r[0] for r in conn.execute(query, values).fetchall()])

    def _exec_update(self, conn) -> Result:
        self._require_filters()
        info = _table_info(conn, self.table)
        sets, values = [], []
        for c, v in self._payload.items():
            sets.append(sql.SQL("{} = ").format(sql.Identifier(c)) + _cast(self._column_type(info, c)))
            values.append(_adapt(v, info.columns[c]))
        where, where_values = self._where(info)
        query = (sql.SQL("update public.{} as x set ").format(sql.Identifier(self.table)) + sql.SQL(", ").join(sets)
                 + where + sql.SQL(" returning to_jsonb(x)"))
        return Result([r[0] for r in conn.execute(query, values + where_values).fetchall()])

    def _exec_delete(self, conn) -> Result:
        self._require_filters()
        info = _table_info(conn, self.table)
        where, values = self._where(info)
        query = sql.SQL("delete from public.{} as x").format(sql.Identifier(self.table)) + where + sql.SQL(" returning to_jsonb(x)")
        return Result([r[0] for r in conn.execute(query, values).fetchall()])


def select_all(build_query, page_size: int = PAGE_SIZE) -> list[dict]:
    """Read every row of a query, page by page.

    ``build_query`` returns a fresh filtered query each call, e.g.
    ``lambda: db.table("t").select("*").eq("user_id", uid).order("id")``.
    """
    rows: list[dict] = []
    while True:
        batch = build_query().range(len(rows), len(rows) + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
