"""AI parameter pipeline: strict validation, logged retries with a fake LLM (no network), loading rules and the
integrity of the committed parameter files against the committed prompt log."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from data_real import ai_params
from data_real.ai_params import (
    GENERATED_DIR,
    TASKS,
    InvalidParamsError,
    MissingParamsError,
    generate,
    load_all,
    load_file,
    validate,
    validate_text,
)
from provenance import LLMGenerationError, LLMResult, read_prompt_log, write_registry
from provenance.prompts import MSG_NO_KEY_VI

ROOT = Path(__file__).resolve().parents[2]
PROMPT_DATA_DIR = ROOT / "data"


@pytest.fixture(scope="module")
def committed():
    return {t: json.loads((GENERATED_DIR / f"{t}.json").read_text(encoding="utf-8")) for t in TASKS}


def _mutated(committed, task, fn):
    data = copy.deepcopy(committed[task]["params"])
    fn(data)
    return validate(task, data)


@pytest.mark.parametrize("task", sorted(TASKS))
def test_committed_params_pass_validation(committed, task):
    assert validate(task, committed[task]["params"]) == []


def _sku(data, sku_id):
    return next(s for s in data["skus"] if s["sku_id"] == sku_id)


@pytest.mark.parametrize(
    ("task", "mutate", "needle"),
    [
        ("catalog", lambda d: _sku(d, "SKU_RAU_MUONG").update(unit_cost_vnd=99_000), "unit_price_vnd >"),
        ("catalog", lambda d: _sku(d, "SKU_GAO_ST25").update(salvage_price_vnd=500_000), "unit_price_vnd >"),
        ("catalog", lambda d: _sku(d, "SKU_TOM_THE").update(shelf_life_days=5), "shelf_life_days (hàng tươi)"),
        ("catalog", lambda d: _sku(d, "SKU_MI_GOI").update(shelf_life_days=10), "shelf_life_days (hàng khô)"),
        ("catalog", lambda d: _sku(d, "SKU_MI_GOI").update(cold_storage_units=0.5), "cold_storage_units = 0"),
        ("catalog", lambda d: _sku(d, "SKU_CA_BASA").update(name_vi="Cá tra (khay)"), "bắt đầu bằng 'Cá basa"),
        ("catalog", lambda d: _sku(d, "SKU_DUONG").update(unit_price_vnd=26_200), "bội số của 500"),
        ("catalog", lambda d: _sku(d, "SKU_DUONG").update(supplier_id="sup duong"), "supplier_id"),
        ("catalog", lambda d: d["skus"].pop(), "phải có đúng 30 SKU"),
        ("catalog", lambda d: d["skus"].append(copy.deepcopy(d["skus"][0])), "phải có đúng 30 SKU"),
        ("catalog", lambda d: d.update(extra=1), "extra"),
        ("catalog", lambda d: d["skus"][0]["basis_vi"].update(price="theo https://gia.example.vn"), "URL"),
        ("catalog", lambda d: d.update(notes_vi="Nguồn: bachhoaxanh.com"), "URL"),
        ("demand", lambda d: d["weekday_factors"]["office"].update(mon_to_sun=[1, 1, 1, 1, 1, 1, 1]), "office"),
        ("demand", lambda d: d["weekday_factors"]["residential"].update(mon_to_sun=[1.0] * 6), "7 giá trị"),
        ("demand", lambda d: d["rain_factors"]["market"].update(heavy_factor=0.95, light_factor=0.9),
         "heavy_factor phải nhỏ hơn"),
        ("demand", lambda d: d["category_base_units"]["meat"].update(office=-1), "category_base_units.meat"),
        ("demand", lambda d: d["promo"]["duration_days"].update(value=3.5), "số nguyên"),
        ("demand", lambda d: d["calendar"]["ram_mung1_plant_uplift"].update(confidence="certain"), "confidence"),
        ("chains", lambda d: d["chains"]["CHAIN_B"]["fresh_affinity"].update(value=1.59), "CHAIN_C > CHAIN_A"),
        ("chains", lambda d: d["chains"]["CHAIN_A"]["price_multiplier"].update(value=0.5), "price_multiplier"),
        ("orders", lambda d: d["basket_units"].update(p_1=0.9), "basket_units"),
        ("orders", lambda d: d["delivery_mode_mix"].update(home=0.2), "delivery_mode_mix"),
        ("orders", lambda d: d["batch_orders_45min"]["office"].update(min=5), "batch_orders_45min.office"),
        ("orders", lambda d: d["earliest_start_max_minutes"].update(value=50), "bội số của 15"),
        ("orders", lambda d: d["hourly_share"]["market"]["shares_6_to_21"].pop(), "16 giá trị"),
        ("elasticity", lambda d: d["elasticity"]["vegetable"].update(value=0.5), "elasticity.vegetable"),
        ("elasticity", lambda d: d["elasticity"]["staple"].update(low=-0.1, value=-0.5), "low ≤ value"),
        ("lots", lambda d: d["dry_lot_age_days"].update(min=50, max=10), "min (50"),
        ("lots", lambda d: (d["fresh_oldest_lot_frac"].update(max=0.9), d["fresh_newest_lot_frac"].update(max=0.6)),
         "fresh_oldest_lot_frac.max"),
    ],
)
def test_validator_rejects_bad_outputs(committed, task, mutate, needle):
    errors = _mutated(committed, task, mutate)
    assert errors and any(needle in e for e in errors), errors


def test_validate_text_rejects_non_json():
    assert validate_text("lots", "đây không phải JSON").startswith("Không phải JSON hợp lệ")
    assert validate_text("lots", "[]")


def _fake_llm(replies):
    calls = []
    it = iter(replies)

    def call(params):
        calls.append(params)
        reply = next(it)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return call, calls


def test_generate_retries_with_errors_and_logs_every_attempt(tmp_path, committed):
    good = json.dumps(committed["lots"]["params"], ensure_ascii=False)
    bad = copy.deepcopy(committed["lots"]["params"])
    bad["dry_lots_count"]["min"] = 9
    llm, calls = _fake_llm([
        LLMResult(json.dumps(bad), "claude-haiku-5-5", "end_turn", {"output_tokens": 10}),
        LLMGenerationError("Dịch vụ AI trả lỗi (mã 529): quá tải"),
        LLMResult(good, "claude-haiku-5-5", "end_turn", {"input_tokens": 5, "output_tokens": 9}, "req_x"),
    ])
    out = generate("lots", data_dir=tmp_path, gen_dir=tmp_path / "gen", llm=llm)
    log = read_prompt_log(tmp_path)
    assert [r["status"] for r in log] == ["invalid", "api_error", "accepted"]
    assert [r["attempt"] for r in log] == [1, 2, 3]
    assert "dry_lots_count.min" in log[0]["error"]
    assert "LẦN TRẢ LỜI TRƯỚC BỊ TỪ CHỐI" not in calls[0]["messages"][0]["content"]
    assert "dry_lots_count.min" in calls[1]["messages"][0]["content"]  # validation error appended
    for c in calls:
        assert c["model"] == "claude-haiku-5-5" and "temperature" not in c
        assert c["output_config"]["format"]["type"] == "json_schema" and c["system"] == ai_params.SYSTEM_VI
    body = json.loads(out.read_text(encoding="utf-8"))
    h = body["header"]
    assert h["prompt_id"] == log[2]["id"] and h["attempt_prompt_ids"] == [r["id"] for r in log]
    assert h["attempt_statuses"] == ["invalid", "api_error", "accepted"]
    assert body["params"] == json.loads(good)
    assert h["response_sha256"] == hashlib.sha256(good.encode()).hexdigest() == log[2]["response_sha256"]
    assert log[2]["parsed_path"] and log[0]["parsed_path"] is None
    assert "temperature" in h["temperature_note_vi"]
    # existing file is kept without --force; with force=True it is regenerated
    assert generate("lots", data_dir=tmp_path, gen_dir=tmp_path / "gen", llm=llm) == out
    assert len(read_prompt_log(tmp_path)) == 3


def test_generate_gives_up_after_three_invalid_attempts(tmp_path):
    llm, calls = _fake_llm([LLMResult("{}", "m", "end_turn")] * 3)
    with pytest.raises(LLMGenerationError) as ei:
        generate("elasticity", data_dir=tmp_path, gen_dir=tmp_path / "gen", llm=llm)
    assert "3 lần" in ei.value.message_vi
    assert [r["status"] for r in read_prompt_log(tmp_path)] == ["invalid"] * 3
    assert not (tmp_path / "gen" / "elasticity.json").exists()


def test_generate_without_key_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMGenerationError) as ei:
        generate("lots", data_dir=tmp_path, gen_dir=tmp_path / "gen")
    assert ei.value.message_vi == MSG_NO_KEY_VI
    assert read_prompt_log(tmp_path) == [] and not (tmp_path / "gen").exists()


def test_generate_refuses_unregistered_dataset(tmp_path, monkeypatch):
    write_registry(tmp_path, {"AI_PARAMS_LOTS": {"kind": "synthetic_code"}})
    llm, calls = _fake_llm([LLMResult("{}", "m", "end_turn")])
    with pytest.raises(LLMGenerationError):
        generate("lots", data_dir=tmp_path, gen_dir=tmp_path / "gen", llm=llm)
    assert calls == []


def test_missing_or_edited_file_fails_in_vietnamese(tmp_path, committed):
    with pytest.raises(MissingParamsError) as ei:
        load_file("demand", tmp_path)
    assert "generate-params --task demand" in str(ei.value) and "Thiếu tệp tham số" in str(ei.value)
    with pytest.raises(MissingParamsError):
        load_all(tmp_path)
    body = copy.deepcopy(committed["chains"])
    body["params"]["chains"]["CHAIN_A"]["dispersion_k"]["value"] = 999
    (tmp_path / "chains.json").write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(InvalidParamsError):
        load_file("chains", tmp_path)


def test_api_schema_is_strict_and_has_no_numeric_keywords():
    def walk(node):
        if isinstance(node, dict):
            assert not {"minimum", "maximum", "minItems", "maxItems", "title"} & set(node)
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False and node["required"] == list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for task in TASKS:
        walk(ai_params.api_schema(task))
    sku_ids = ai_params.api_schema("catalog")["$defs"]["SkuParams"]["properties"]["sku_id"]["enum"]
    assert sku_ids == list(ai_params.SKU_IDS)


# ---------------------------------------------------------------- committed artifacts


def test_committed_files_match_the_committed_prompt_log(committed):
    log = {r["id"]: r for r in read_prompt_log(PROMPT_DATA_DIR)}
    assert log, "data/provenance/prompts.jsonl is missing"
    for task, body in committed.items():
        h = body["header"]
        assert h["task"] == task and h["dataset_id"] == TASKS[task].dataset_id
        assert h["prompt_id"] == h["attempt_prompt_ids"][-1] and h["attempt_statuses"][-1] == "accepted"
        for pid in h["attempt_prompt_ids"]:
            rec = log[pid]
            assert rec["task"] == task and rec["dataset_id"] == h["dataset_id"]
            assert rec["prompt"] and rec["system"]
            assert hashlib.sha256(rec["prompt"].encode()).hexdigest() == rec["prompt_sha256"]
            assert rec["parameters"]["model"] == rec["model"] == "claude-haiku-5-5"
            assert "temperature" not in rec["parameters"]
        rec = log[h["prompt_id"]]
        assert rec["status"] == "accepted" and rec["parsed_path"] == f"data_real/generated/{task}.json"
        text = (PROMPT_DATA_DIR / rec["response_path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode()).hexdigest() == rec["response_sha256"] == h["response_sha256"]
        assert json.loads(text) == body["params"], f"{task}: params differ from the logged response"
        assert rec["usage"]["output_tokens"] > 0


def test_no_secret_anywhere_in_committed_provenance():
    files = [p for root in (PROMPT_DATA_DIR / "provenance", GENERATED_DIR) for p in root.rglob("*") if p.is_file()]
    assert len(files) >= len(TASKS) + 3
    for path in files:
        assert "sk-ant" not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_registry_updates_expose_prompt_ids(committed):
    up = ai_params.registry_updates()
    union = []
    for task, body in committed.items():
        entry = up[TASKS[task].dataset_id]
        assert entry["prompt_ids"] == body["header"]["attempt_prompt_ids"]
        union += entry["prompt_ids"]
    assert up[ai_params.DERIVED_ID]["prompt_ids"] == union
    assert set(up[ai_params.DERIVED_ID]["details"]["parents"]) >= {t.dataset_id for t in TASKS.values()}
