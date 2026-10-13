import sqlite3

import pytest

from agent.sql_guard import (
    DEFAULT_VIEWS,
    SqlGuardError,
    make_query_data_tool,
    run_query_data,
    validate_readonly_sql,
)
from agent.tools import ToolContext, ToolError, ToolRegistry
from tests.agent.helpers import make_chain_db


@pytest.fixture
def db(tmp_path):
    return make_chain_db(tmp_path / "chain.sqlite")


def test_valid_select_is_rewritten_with_chain_filter_and_limit():
    out = validate_readonly_sql(
        "SELECT store_id, SUM(units) AS u FROM v_sales_daily GROUP BY store_id", "CHAIN_A", DEFAULT_VIEWS, 50
    )
    assert "(SELECT * FROM v_sales_daily WHERE chain_id = :chain_id) AS v_sales_daily" in out
    assert out.rstrip().endswith("LIMIT 50")
    assert out.startswith("SELECT * FROM (")


def test_alias_is_preserved():
    out = validate_readonly_sql(
        "SELECT s.name, k.qty FROM v_stores AS s JOIN v_stock k ON k.store_id = s.store_id",
        "CHAIN_A",
        DEFAULT_VIEWS,
        10,
    )
    assert "WHERE chain_id = :chain_id) AS s" in out
    assert "WHERE chain_id = :chain_id) k" in out


def test_trailing_semicolon_allowed():
    validate_readonly_sql("SELECT * FROM v_stores;", "CHAIN_A", DEFAULT_VIEWS, 10)


INJECTIONS = [
    "SELECT * FROM v_stores; DROP TABLE stores",
    "SELECT * FROM v_stores;DROP TABLE stores;",
    "DROP TABLE stores",
    "DELETE FROM stores",
    "UPDATE stores SET name='x'",
    "INSERT INTO stores(store_id) VALUES('x')",
    "SELECT * FROM v_stores UNION SELECT user_id, chain_id, username, password_hash, 1, 1, 1, 1 FROM users",
    "SELECT * FROM v_stores WHERE store_id IN (SELECT name FROM sqlite_master)",
    "SELECT (SELECT sql FROM sqlite_master LIMIT 1) FROM v_stores",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM main.sqlite_master",
    "SELECT * FROM main.stores",
    "SELECT * FROM stores",
    "SELECT * FROM daily_sales",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "SELECT * FROM v_stores -- comment",
    "SELECT * FROM v_stores /* c */",
    "PRAGMA table_info(stores)",
    "SELECT * FROM pragma_table_info('stores')",
    "SELECT load_extension('evil')",
    "SELECT readfile('/etc/passwd') FROM v_stores",
    "SELECT writefile('/tmp/x', 'y') FROM v_stores",
    "SELECT * FROM v_stores, users",
    "SELECT * FROM v_stores a JOIN users b ON 1=1",
    "SELECT * FROM v_stores WHERE store_id IN users",
    'SELECT * FROM "users"',
    "SELECT * FROM `users`",
    "SELECT * FROM [users]",
    "WITH x AS (SELECT * FROM users) SELECT * FROM x",
    "SELECT * FROM v_stores WHERE chain_id = ?",
    "SELECT * FROM v_stores WHERE chain_id = :chain_id",
    "SELECT randomblob(1000000000) FROM v_stores",
    "SELECT * FROM json_each('[1]')",
    "SELECT * FROM v_stores\x00",
    "",
    "   ",
    "SELECT 'unterminated FROM v_stores",
    "VALUES (1)",
    "REPLACE INTO stores(store_id) VALUES ('x')",
    "VACUUM",
    "SELECT * FROM (SELECT * FROM users)",
]


@pytest.mark.parametrize("sql", INJECTIONS)
def test_injection_attempts_rejected(sql):
    with pytest.raises(SqlGuardError) as ei:
        validate_readonly_sql(sql, "CHAIN_A", DEFAULT_VIEWS, 10)
    assert ei.value.message_vi


def test_strings_containing_keywords_are_fine(db):
    res = run_query_data(db, "SELECT name FROM v_stores WHERE name <> 'DROP TABLE users; --'", "CHAIN_A")
    assert sorted(r[0] for r in res["rows"]) == ["CH Quận 1", "CH Quận 3"]


def test_view_not_in_allowed_list_rejected():
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("SELECT * FROM v_stock", "CHAIN_A", ["v_stores"], 10)


def test_bad_chain_id_rejected():
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("SELECT * FROM v_stores", "A' OR 1=1 --", DEFAULT_VIEWS, 10)


def test_run_filters_chain_even_with_or_bypass(db):
    res = run_query_data(db, "SELECT store_id FROM v_stores WHERE chain_id = 'CHAIN_B' OR 1=1", "CHAIN_A")
    assert sorted(r[0] for r in res["rows"]) == ["A1", "A2"]
    res = run_query_data(db, "SELECT SUM(units) AS total FROM v_sales_daily", "CHAIN_A")
    assert res["columns"] == ["total"] and res["rows"] == [[102]]
    res = run_query_data(db, "SELECT COUNT(*) FROM v_sales_daily a, v_sales_daily b", "CHAIN_A")
    assert res["rows"] == [[9]]


def test_run_union_between_views_still_filtered(db):
    res = run_query_data(
        db, "SELECT store_id FROM v_stock UNION SELECT store_id FROM v_online_orders", "CHAIN_A"
    )
    assert [r[0] for r in res["rows"]] == ["A1"]


def test_run_enforces_limit_and_reports_truncation(db):
    res = run_query_data(db, "SELECT * FROM v_sales_daily", "CHAIN_A", max_rows=2)
    assert res["row_count"] == 2 and res["truncated"] is True
    res = run_query_data(db, "SELECT * FROM v_sales_daily", "CHAIN_A", max_rows=10)
    assert res["row_count"] == 3 and res["truncated"] is False


def test_online_orders_view_has_no_customer_fields(db):
    res = run_query_data(db, "SELECT * FROM v_online_orders", "CHAIN_A")
    assert "customer_name" not in res["columns"] and "phone" not in res["columns"]
    assert res["rows"][0][res["columns"].index("lat")] == 10.771


def test_connection_is_read_only(db):
    from agent.sql_guard import _connect_readonly

    con = _connect_readonly(db, DEFAULT_VIEWS)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM stores")
    con.close()


def test_authorizer_blocks_direct_table_reads_even_if_validator_bypassed(db):
    from agent.sql_guard import _connect_readonly

    con = _connect_readonly(db, DEFAULT_VIEWS)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("SELECT password_hash FROM users").fetchall()
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("SELECT name FROM sqlite_master").fetchall()
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("SELECT hex(randomblob(4)) FROM v_stores").fetchall()
    assert con.execute("SELECT COUNT(store_id) FROM v_stores").fetchone()[0] == 3
    # Bare COUNT(*) on a view is optimised into a base-table read outside the view context; the strict
    # authorizer refuses it (validated queries never hit this path because views are wrapped in subqueries).
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("SELECT COUNT(*) FROM v_stores").fetchall()
    con.close()


def test_missing_db_gives_vietnamese_error(tmp_path):
    with pytest.raises(SqlGuardError, match="dữ liệu"):
        run_query_data(tmp_path / "nope.sqlite", "SELECT * FROM v_stores", "CHAIN_A")


def test_query_data_tool(db):
    reg = ToolRegistry()
    seen = []

    def provenance_for(chain, tables):
        seen.append((chain, list(tables)))
        return {"sources": ["ds_x"], "source_labels_vi": ["Bộ X"]}

    reg.register(make_query_data_tool(lambda chain: db, provenance_for=provenance_for))
    ctx = ToolContext(chain_id="CHAIN_A", actor="owner_a", extras={"role": "owner"})
    res = reg.call("query_data", {"sql": "SELECT SUM(qty) AS qty FROM v_stock"}, ctx)
    assert res.data["rows"] == [[30]]
    # provenance is computed from the base tables actually read through the view
    assert res.data["tables"] == ["inventory_lots", "stores"] and seen == [
        ("CHAIN_A", ["inventory_lots", "stores"])
    ]
    assert res.data["sources"] == ["ds_x"] and res.data["source_labels_vi"] == ["Bộ X"]
    assert "query_data:v_stock" in res.citations
    with pytest.raises(ToolError, match="SELECT"):
        reg.call("query_data", {"sql": "DELETE FROM stores"}, ctx)


def test_query_data_without_provenance_hook_claims_no_source(db):
    reg = ToolRegistry()
    reg.register(make_query_data_tool(lambda chain: db))
    ctx = ToolContext(chain_id="CHAIN_A", actor="owner_a", extras={"role": "owner"})
    res = reg.call("query_data", {"sql": "SELECT name FROM v_skus"}, ctx)
    assert "sources" not in res.data and res.data["tables"] == ["skus"]


def test_store_scope_filters_store_views_and_binds_parameter(db):
    out = validate_readonly_sql("SELECT * FROM v_sales_daily", "CHAIN_A", DEFAULT_VIEWS, 50, store_id="A1")
    assert "WHERE chain_id = :chain_id AND store_id = :store_id" in out
    res = run_query_data(db, "SELECT DISTINCT store_id FROM v_sales_daily", "CHAIN_A", store_id="A1")
    assert res["rows"] == [["A1"]]
    # Without a store scope (owner) the whole chain is visible.
    full = run_query_data(db, "SELECT DISTINCT store_id FROM v_sales_daily", "CHAIN_A")
    assert {r[0] for r in full["rows"]} >= {"A1", "A2"}


def test_store_scope_cannot_be_bypassed_with_or_or_subselect(db):
    res = run_query_data(
        db,
        "SELECT DISTINCT store_id FROM v_sales_daily WHERE 1=1 OR store_id = 'A2'",
        "CHAIN_A",
        store_id="A1",
    )
    assert res["rows"] == [["A1"]]
    res = run_query_data(
        db,
        "SELECT DISTINCT store_id FROM (SELECT * FROM v_sales_daily) ",
        "CHAIN_A",
        store_id="A1",
    )
    assert res["rows"] == [["A1"]]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM (v_stores)",
        "SELECT * FROM (users)",
        "SELECT * FROM v_stock NATURAL JOIN (inventory_lots)",
        "SELECT * FROM v_stores, (v_skus)",
    ],
)
def test_parenthesised_table_names_rejected(sql):
    with pytest.raises(SqlGuardError):
        validate_readonly_sql(sql, "CHAIN_A", DEFAULT_VIEWS, 50)


def test_tool_scopes_store_manager_but_not_owner(db):
    tool = make_query_data_tool(db)
    reg = ToolRegistry()
    reg.register(tool)
    sql = {"sql": "SELECT DISTINCT store_id FROM v_sales_daily"}
    mgr = reg.call("query_data", sql, ToolContext("CHAIN_A", "m", "A1", {"role": "store_manager"}))
    assert mgr.data["rows"] == [["A1"]]
    owner = reg.call("query_data", sql, ToolContext("CHAIN_A", "o", None, {"role": "owner"}))
    assert len(owner.data["rows"]) >= 2


def test_sql_error_text_is_generic(db):
    with pytest.raises(SqlGuardError) as exc:
        run_query_data(db, "SELECT nosuchcolumn FROM v_stores", "CHAIN_A")
    assert "nosuchcolumn" not in str(exc.value)


def test_non_owner_without_store_fails_closed(db):
    """HIGH-1: a store manager whose token carries no store must not get the whole chain."""
    reg = ToolRegistry()
    reg.register(make_query_data_tool(db))
    sql = {"sql": "SELECT DISTINCT store_id FROM v_sales_daily"}
    for ctx in (
        ToolContext("CHAIN_A", "m", None, {"role": "store_manager"}),
        ToolContext("CHAIN_A", "m", None, {}),  # missing role = not owner
    ):
        with pytest.raises(ToolError, match="cửa hàng"):
            reg.call("query_data", sql, ctx)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 987654 AS x",
        "SELECT 987654",
        "SELECT (SELECT 987654) AS x",
        "SELECT 1 WHERE 1 = 1",
    ],
)
def test_query_without_view_reference_rejected(sql):
    """HIGH-2: FROM-less / view-less SELECTs only echo literals the model wrote."""
    with pytest.raises(SqlGuardError, match="view"):
        validate_readonly_sql(sql, "CHAIN_A", DEFAULT_VIEWS, 50)


def test_literal_numbers_from_query_data_are_not_verified_sources(db):
    """HIGH-2: numbers the model typed into SQL (literals, LIMIT) never verify an answer."""
    from agent.guardrail import verify_numbers

    reg = ToolRegistry()
    reg.register(make_query_data_tool(db))
    owner = ToolContext("CHAIN_A", "o", None, {"role": "owner"})
    with pytest.raises(ToolError):
        reg.call("query_data", {"sql": "SELECT 987654 AS x"}, owner)
    res = reg.call("query_data", {"sql": "SELECT store_id FROM v_stores WHERE 987654 > 0 LIMIT 3"}, owner)
    assert not verify_numbers("Doanh số là 987.654 đ.", [res]).ok
    assert verify_numbers(f"Có {res.data['row_count']} cửa hàng.", [res]).ok


def test_like_and_glob_are_allowed(db):
    """MED-3: LIKE/GLOB compile to SQLite functions; the authorizer must allow them."""
    res = run_query_data(db, "SELECT DISTINCT sku_id FROM v_stock WHERE sku_id LIKE 'SKU%'", "CHAIN_A")
    res2 = run_query_data(db, "SELECT DISTINCT sku_id FROM v_stock WHERE sku_id GLOB '*'", "CHAIN_A")
    assert res["rows"] == [r for r in res2["rows"] if r[0].startswith("SKU")]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 987654 AS x FROM v_stores",
        "SELECT round(987654, 0) AS x FROM v_stores",
        "SELECT '987654' AS x FROM v_stores",
        "SELECT 12.5 + units FROM v_sales_daily",
        "SELECT 9*9*9*9 AS x FROM v_stock",
        "SELECT 5||5 AS x FROM v_stock",
        "SELECT length('aaaaaaaaaaaaa') AS x FROM v_stock",
        "SELECT x FROM (SELECT 4*5 AS x FROM v_stock)",
        "SELECT round(9*9*9*9, 0) AS x FROM v_stock",
        "SELECT store_id, 5 FROM v_stores",
        "SELECT max(units, 12) FROM v_sales_daily",
    ],
)
def test_literal_values_in_select_list_rejected(sql):
    with pytest.raises(SqlGuardError):
        validate_readonly_sql(sql, "CHAIN_A", DEFAULT_VIEWS, 50)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT store_id, SUM(units) FROM v_sales_daily WHERE units > 100 GROUP BY store_id LIMIT 20",
        "SELECT count(*) FROM v_stock WHERE qty >= 10",
        "SELECT round(avg(units)) FROM v_sales_daily",
        "SELECT round(avg(units), 1) FROM v_sales_daily",
        "SELECT sum(units) / count(*) FROM v_sales_daily",
    ],
)
def test_ordinary_literals_outside_select_list_allowed(sql):
    validate_readonly_sql(sql, "CHAIN_A", DEFAULT_VIEWS, 50)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM (SELECT units FROM v_sales_daily LIMIT 6561)",
        "SELECT count(*) * count(*) FROM (SELECT units FROM v_sales_daily LIMIT 9)",
        "SELECT count(*) FROM (SELECT units FROM v_sales_daily LIMIT 5 OFFSET 2)",
    ],
)
def test_nested_limit_cannot_mint_numbers(sql):
    with pytest.raises(SqlGuardError):
        validate_readonly_sql(sql, "CHAIN_A", DEFAULT_VIEWS, 50)


def test_outer_limit_still_allowed():
    validate_readonly_sql("SELECT sku_id FROM v_skus ORDER BY sku_id LIMIT 20", "CHAIN_A", DEFAULT_VIEWS, 50)


def test_view_columns_hint_accepts_relative_paths(db, monkeypatch):
    from agent.sql_guard import view_columns_hint

    monkeypatch.chdir(db.parent)
    hint = view_columns_hint(db.name)
    assert hint.startswith("Cột có sẵn") and "v_sales_daily(" in hint
