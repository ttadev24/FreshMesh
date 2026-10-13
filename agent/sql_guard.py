"""Read-only text-to-SQL guard for the ``query_data`` tool.

Two independent layers:

1. ``validate_readonly_sql`` tokenises the query (no regex on raw SQL) and accepts only a single
   ``SELECT`` statement without comments, parameters, quoted identifiers, CTEs or write/DDL keywords.
   Every table position (after ``FROM``/``JOIN``/comma in a FROM clause, or ``IN <table>``) must name a
   whitelisted view, and only allow-listed SQL functions may be called. Each view reference is then
   *replaced* by ``(SELECT * FROM <view> WHERE chain_id = :chain_id)`` so no predicate the user writes
   (e.g. ``OR 1=1``) can widen the tenant filter, and the whole query is wrapped with ``LIMIT``.
2. ``run_query_data`` executes on a ``file:...?mode=ro`` connection with ``PRAGMA query_only`` and an
   SQLite authorizer that only permits SELECT, reads of whitelisted views (or of base tables *through*
   those views) and allow-listed functions, plus a VM-step budget against runaway joins.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from agent.tools import Tool, ToolContext, ToolError, ToolResult

log = logging.getLogger(__name__)

DEFAULT_VIEWS: tuple[str, ...] = ("v_sales_daily", "v_stock", "v_stores", "v_skus", "v_online_orders")
DEFAULT_MAX_ROWS = 200
MAX_VM_STEPS = 5_000_000

ALLOWED_FUNCTIONS = frozenset(
    {
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "total",
        "round",
        "abs",
        "coalesce",
        "ifnull",
        "nullif",
        "iif",
        "date",
        "datetime",
        "strftime",
        "julianday",
        "lower",
        "upper",
        "substr",
        "length",
        "trim",
        "instr",
        "group_concat",
        "like",  # ``x LIKE y`` / ``x GLOB y`` are compiled to these SQL functions
        "glob",
    }
)
_KEYWORDS = frozenset(
    {
        "SELECT",
        "FROM",
        "WHERE",
        "GROUP",
        "BY",
        "ORDER",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "AS",
        "AND",
        "OR",
        "NOT",
        "IN",
        "IS",
        "NULL",
        "LIKE",
        "GLOB",
        "BETWEEN",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "JOIN",
        "LEFT",
        "RIGHT",
        "FULL",
        "INNER",
        "OUTER",
        "CROSS",
        "NATURAL",
        "ON",
        "USING",
        "DISTINCT",
        "ASC",
        "DESC",
        "UNION",
        "ALL",
        "EXCEPT",
        "INTERSECT",
        "EXISTS",
        "CAST",
        "OVER",
        "PARTITION",
        "ESCAPE",
        "COLLATE",
        "NOCASE",
        "INTEGER",
        "REAL",
        "TEXT",
        "NUMERIC",
        "TRUE",
        "FALSE",
        "NULLS",
        "FIRST",
        "LAST",
        "FILTER",
    }
)
_FORBIDDEN = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "REPLACE",
        "VACUUM",
        "REINDEX",
        "ANALYZE",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE",
        "INTO",
        "WITH",
        "VALUES",
        "TRIGGER",
        "INDEX",
        "TABLE",
        "VIEW",
        "RECURSIVE",
        "UPSERT",
        "CONFLICT",
        "DO",
        "WINDOW",
        "TEMP",
        "TEMPORARY",
        "MAIN",
        "RETURNING",
        "MATERIALIZED",
        "EXPLAIN",
    }
)
# Keywords that end a FROM clause at the current nesting depth.
_FROM_END = frozenset(
    {"WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "UNION", "EXCEPT", "INTERSECT", "SELECT"}
)
_CHAIN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TOKEN_RE = re.compile(
    r"""(?P<ws>\s+)
      |(?P<str>'(?:[^']|'')*')
      |(?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
      |(?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      |(?P<op><=|>=|<>|!=|==|\|\||[(),.*+\-/%<>=])
    """,
    re.VERBOSE,
)


class SqlGuardError(ToolError):
    pass


def _tokenize(sql: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(sql):
        if sql.startswith(("--", "/*"), pos):
            raise SqlGuardError("Câu truy vấn không được chứa chú thích (comment).")
        if sql[pos] == ";":
            raise SqlGuardError("Chỉ cho phép một câu SELECT duy nhất.")
        m = _TOKEN_RE.match(sql, pos)
        if not m:
            raise SqlGuardError(f"Ký tự không được phép trong câu truy vấn: {sql[pos]!r}.")
        kind = m.lastgroup or ""
        if kind != "ws":
            tokens.append((kind, m.group(0)))
        pos = m.end()
    return tokens


def _reject_literal_values_in_select_list(tokens: list[tuple[str, str]]) -> None:
    """A model must not be able to launder an invented figure through ``query_data`` (its rows are a number
    source for the answer guardrail). In a SELECT list no string literal is allowed, and a numeric literal is
    only allowed as a single-digit function argument after a comma (``round(avg(x), 1)``); that rules out
    ``SELECT 987654``, ``SELECT 9*9*9*9`` and ``SELECT 5||5`` alike. WHERE/LIMIT literals are unaffected."""
    state: dict[int, str] = {}  # depth -> "top" (the SELECT list itself) | "args" (inside parentheses of it)
    depth = 0
    prev = ""
    for kind, text in tokens:
        upper = text.upper()
        if kind == "ident" and upper == "SELECT":
            state[depth] = "top"
        elif kind == "ident" and upper == "FROM":
            state.pop(depth, None)
        elif text == "(":
            if depth in state:
                state[depth + 1] = "args"
            depth += 1
        elif text == ")":
            state.pop(depth, None)
            depth -= 1
        elif depth in state and kind in {"num", "str"}:
            allowed = kind == "num" and state[depth] == "args" and prev == "," and len(text) == 1
            if not allowed:
                raise SqlGuardError("Không được đưa hằng số vào danh sách cột; hãy chọn cột từ view.")
        prev = text


STORE_SCOPED_VIEWS = frozenset({"v_sales_daily", "v_stock", "v_stores", "v_online_orders"})


def validate_readonly_sql(
    sql: str,
    chain_id: str,
    allowed_views: Iterable[str] = DEFAULT_VIEWS,
    max_rows: int = DEFAULT_MAX_ROWS,
    store_id: str | None = None,
) -> str:
    """Return a rewritten, tenant-filtered, LIMITed query using the named parameter ``:chain_id``.

    With ``store_id`` set (store-manager scope) views that have a ``store_id`` column are additionally
    filtered by the bound parameter ``:store_id``."""
    if not _CHAIN_RE.match(chain_id or ""):
        raise SqlGuardError("Mã chuỗi không hợp lệ.")
    if max_rows < 1:
        raise SqlGuardError("Giới hạn số dòng không hợp lệ.")
    views = {v.lower() for v in allowed_views}
    body = sql.strip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
    tokens = _tokenize(body)
    if not tokens or tokens[0][1].upper() != "SELECT":
        raise SqlGuardError("Chỉ cho phép câu lệnh SELECT trên các view được phép.")

    _reject_literal_values_in_select_list(tokens)

    out: list[str] = []
    view_refs = 0
    depth = 0
    from_active: dict[int, bool] = {}
    prev_upper = ""
    i = 0
    while i < len(tokens):
        kind, text = tokens[i]
        upper = text.upper()
        nxt = tokens[i + 1][1] if i + 1 < len(tokens) else ""
        if kind == "ident":
            low = text.lower()
            if upper in _FORBIDDEN or low.startswith(("sqlite_", "pragma_")):
                raise SqlGuardError(f"Từ khóa hoặc đối tượng '{text}' không được phép.")
            if upper in {"LIMIT", "OFFSET"} and depth > 0:
                # A nested LIMIT n would let a query mint the number n (e.g. count(*) over LIMIT 6561).
                raise SqlGuardError("Chỉ được dùng LIMIT/OFFSET ở câu SELECT ngoài cùng.")
            if nxt == "(" and upper not in _KEYWORDS and low not in ALLOWED_FUNCTIONS:
                raise SqlGuardError(f"Hàm '{text}' không được phép.")
            table_pos = prev_upper in {"FROM", "JOIN"} or (
                prev_upper == "," and from_active.get(depth, False)
            )
            if prev_upper == "IN" and nxt != "(":
                raise SqlGuardError("Không được dùng 'IN <bảng>'; hãy dùng truy vấn con trên view được phép.")
            if table_pos:
                if low not in views or nxt in {".", "("}:
                    raise SqlGuardError(
                        f"Chỉ được truy vấn các view: {', '.join(sorted(views))}. '{text}' không được phép."
                    )
                has_alias = nxt.upper() == "AS" or (
                    i + 1 < len(tokens) and tokens[i + 1][0] == "ident" and nxt.upper() not in _KEYWORDS
                )
                scope = " AND store_id = :store_id" if store_id and low in STORE_SCOPED_VIEWS else ""
                out.append(f"(SELECT * FROM {low} WHERE chain_id = :chain_id{scope})")
                view_refs += 1
                if not has_alias:
                    out.append(f"AS {low}")
                prev_upper = "VIEW_REF"
                i += 1
                continue
            if upper == "FROM":
                from_active[depth] = True
            elif upper in _FROM_END:
                from_active[depth] = False
        elif text == "(":
            if (prev_upper in {"FROM", "JOIN"} or (prev_upper == "," and from_active.get(depth, False))) and (
                nxt.upper() != "SELECT"
            ):
                raise SqlGuardError("Không được đặt tên bảng trong ngoặc; hãy truy vấn trực tiếp view.")
            depth += 1
            from_active[depth] = False
        elif text == ")":
            from_active.pop(depth, None)
            depth -= 1
            if depth < 0:
                raise SqlGuardError("Dấu ngoặc không cân bằng.")
        out.append(text)
        prev_upper = upper
        i += 1
    if depth != 0:
        raise SqlGuardError("Dấu ngoặc không cân bằng.")
    if not view_refs:
        # A SELECT that reads no view only echoes literals the model wrote; such numbers must never
        # become "verified" sources for the number guardrail.
        raise SqlGuardError(
            f"Câu truy vấn phải đọc dữ liệu từ ít nhất một view được phép: {', '.join(sorted(views))}."
        )
    return f"SELECT * FROM ({' '.join(out)}) LIMIT {int(max_rows)}"


def _connect_readonly(
    db_path: Path | str, allowed_views: Iterable[str], tables_read: set[str] | None = None
) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise SqlGuardError("Không tìm thấy cơ sở dữ liệu của chuỗi.")
    con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    views = {v.lower() for v in allowed_views}

    def authorizer(
        action: int, arg1: str | None, arg2: str | None, _db: str | None, source: str | None
    ) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            table = (arg1 or "").lower()
            if table in views or (source or "").lower() in views:
                if tables_read is not None and table not in views:
                    tables_read.add(table)  # base table read through a whitelisted view (provenance)
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    con.set_authorizer(authorizer)
    steps = {"n": 0}

    def progress() -> int:
        steps["n"] += 1000
        return 1 if steps["n"] > MAX_VM_STEPS else 0

    con.set_progress_handler(progress, 1000)
    return con


def run_query_data(
    db_path: Path | str,
    sql: str,
    chain_id: str,
    *,
    allowed_views: Sequence[str] = DEFAULT_VIEWS,
    max_rows: int = DEFAULT_MAX_ROWS,
    store_id: str | None = None,
) -> dict[str, Any]:
    """Validate and execute; returns ``{columns, rows, row_count, truncated, views, tables, sql}``
    (``tables`` = base tables actually read through the views, for data provenance)."""
    safe_sql = validate_readonly_sql(sql, chain_id, allowed_views, max_rows + 1, store_id)
    used = sorted({v for v in allowed_views if re.search(rf"\bFROM {re.escape(v.lower())} WHERE", safe_sql)})
    tables: set[str] = set()
    con = _connect_readonly(db_path, allowed_views, tables)
    try:
        cur = con.execute(safe_sql, {"chain_id": chain_id, "store_id": store_id})
        columns = [d[0] for d in cur.description or []]
        rows = [list(r) for r in cur.fetchall()]
    except sqlite3.DatabaseError as exc:
        log.warning("query_data failed: %s", exc)  # raw (English) text stays in the server log
        msg = str(exc).lower()
        if "interrupted" in msg:
            raise SqlGuardError("Truy vấn chạy quá lâu và đã bị dừng.") from None
        if "not authorized" in msg or "prohibited" in msg:
            raise SqlGuardError("Truy vấn truy cập đối tượng không được phép.") from None
        raise SqlGuardError("Truy vấn không hợp lệ (cột hoặc cú pháp không đúng).") from None
    finally:
        con.close()
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "views": used,
        "tables": sorted(tables),
        "sql": safe_sql,
    }


def view_columns_hint(db_path: Path | str, views: Sequence[str] = DEFAULT_VIEWS) -> str:
    """ "Cột: v_x(a, b); ..." read from the DB itself, so the model never has to guess column names
    (``chain_id`` and ``source`` are omitted: the tenant filter and provenance are handled by the system)."""
    path = Path(db_path).resolve()
    if not path.is_file():
        return ""
    con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        parts = []
        for v in views:
            cols = [r[0] for r in con.execute("SELECT name FROM pragma_table_info(?)", (v,))]
            cols = [c for c in cols if c not in ("chain_id", "source")]
            if cols:
                parts.append(f"{v}({', '.join(cols)})")
    finally:
        con.close()
    return ("Cột có sẵn (chỉ dùng các cột này): " + "; ".join(parts) + ".") if parts else ""


QUERY_DATA_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
            "description": "Một câu SELECT trên các view được phép (không cần lọc chain_id).",
        },
        "purpose_vi": {"type": "string", "maxLength": 300, "description": "Mục đích truy vấn."},
    },
    "required": ["sql"],
    "additionalProperties": False,
}


def make_query_data_tool(
    db_path_for: Callable[[str], Path | str] | Path | str,
    *,
    allowed_views: Sequence[str] = DEFAULT_VIEWS,
    max_rows: int = DEFAULT_MAX_ROWS,
    schema_hint_vi: str = "",
    provenance_for: Callable[[str, Sequence[str]], dict[str, Any]] | None = None,
) -> Tool:
    """``query_data`` read tool. ``db_path_for(chain_id)`` maps the caller's tenant to its DB file;
    ``provenance_for(chain_id, tables)`` returns ``{sources, source_labels_vi}`` for the base tables read
    (without it the output carries no provenance and the agent reports "không rõ nguồn")."""

    def fn(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = db_path_for(ctx.chain_id) if callable(db_path_for) else db_path_for
        if ctx.extras.get("role") == "owner":
            scope_store = None
        elif ctx.store_id:
            scope_store = ctx.store_id
        else:  # fail closed: a non-owner without a store must never see the whole chain
            raise SqlGuardError("Tài khoản chưa gắn với cửa hàng nào nên không thể truy vấn dữ liệu.")
        result = run_query_data(
            path,
            args["sql"],
            ctx.chain_id,
            allowed_views=allowed_views,
            max_rows=max_rows,
            store_id=scope_store,
        )
        if provenance_for is not None:
            result.update(provenance_for(ctx.chain_id, result["tables"]))
        return ToolResult(data=result, citations=[f"query_data:{v}" for v in result["views"]])

    description = (
        "Truy vấn số liệu chỉ đọc bằng một câu SQL SELECT trên các view: "
        + ", ".join(allowed_views)
        + f". Hệ thống tự lọc theo chuỗi của người dùng và giới hạn {max_rows} dòng."
        + (f" {schema_hint_vi}" if schema_hint_vi else "")
    )
    return Tool("query_data", description, QUERY_DATA_SCHEMA, "read", fn)
