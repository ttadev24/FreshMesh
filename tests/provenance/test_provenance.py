import json
import sqlite3

import pytest

from provenance import (
    SYNTHETIC_LABEL_VI,
    Dataset,
    LLMGenerationError,
    LLMResult,
    describe,
    get_prompt,
    label_vi,
    llm_generate,
    load_registry,
    log_prompt,
    read_prompt_log,
    record_raw_file,
    sources_for,
    verify_manifest,
    write_registry,
)
from provenance.__main__ import main


def test_defaults_load_without_data_dir(tmp_path):
    reg = load_registry(tmp_path)
    assert {"OSM_HCMC", "CALENDAR_VN", "GEN_PROGRAM_V1", "WEATHER_OPENMETEO_ARCHIVE"} <= set(reg)
    for ds in reg.values():
        assert isinstance(ds, Dataset) and ds.description_vi and ds.name_vi
        if ds.kind == "public":
            assert ds.url and ds.license
    assert "SIMULATED" not in reg


def test_labels(tmp_path):
    reg = load_registry(tmp_path)
    assert label_vi("OSM_HCMC", reg) == "© OpenStreetMap contributors (ODbL)"
    assert label_vi("GEN_PROGRAM_V1", reg) == SYNTHETIC_LABEL_VI
    assert "ODbL" in label_vi("OSM_HCMC_SITES", reg)
    assert label_vi("NOPE", reg) == "Nguồn chưa đăng ký (NOPE)"


def test_pipeline_registry_overlays_defaults(tmp_path):
    write_registry(
        tmp_path, {"OSM_HCMC": {"retrieved_at": "2026-10-13T07:00:00+00:00", "details": {"elements": 5}}}
    )
    reg = load_registry(tmp_path)
    assert reg["OSM_HCMC"].retrieved_at == "2026-10-13T07:00:00+00:00"
    assert reg["OSM_HCMC"].license == "ODbL 1.0"
    d = describe("OSM_HCMC", reg, tmp_path)
    assert d["details"] == {"elements": 5} and d["label_vi"].startswith("©")
    with pytest.raises(KeyError):
        describe("NOPE", reg, tmp_path)
    with pytest.raises(ValueError):
        write_registry(tmp_path, {"X": {"id": "X", "name_vi": "x", "kind": "bogus", "description_vi": "x"}})


def test_sources_for_merges_row_sources_and_table_map():
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE stores(store_id TEXT, source TEXT);"
        "CREATE TABLE weather(date TEXT, rain_mm REAL);"
        "CREATE TABLE data_sources(table_name TEXT, column_name TEXT, dataset_id TEXT);"
        "INSERT INTO stores VALUES ('a','OSM_HCMC_SITES'),('b','OSM_HCMC_SITES');"
        "INSERT INTO data_sources VALUES ('weather','rain_mm','WEATHER_OPENMETEO_ARCHIVE'),"
        "('weather','rain_mm','WEATHER_OPENMETEO_FORECAST');"
    )
    assert sources_for(con, ["stores"]) == ["OSM_HCMC_SITES"]
    assert sources_for(con, ["stores", "weather"]) == [
        "OSM_HCMC_SITES",
        "WEATHER_OPENMETEO_ARCHIVE",
        "WEATHER_OPENMETEO_FORECAST",
    ]
    with pytest.raises(ValueError):
        sources_for(con, ["stores; DROP TABLE stores"])


AI_DS = {
    "id": "AI_PARAMS_TEST",
    "name_vi": "Tham số do AI đề xuất (thử)",
    "kind": "ai_generated",
    "url": None,
    "license": None,
    "description_vi": "Bộ thử nghiệm.",
}


def test_log_prompt_and_registry_attach(tmp_path):
    with pytest.raises(LLMGenerationError):  # AI output can never be logged under a non-AI dataset
        log_prompt(
            prompt="x", response="y", purpose="p", dataset_id="GEN_PROGRAM_V1", model="m", data_dir=tmp_path
        )
    with pytest.raises(LLMGenerationError):
        log_prompt(prompt="x", response="y", purpose="p", dataset_id="UNKNOWN", model="m", data_dir=tmp_path)
    write_registry(tmp_path, {"AI_PARAMS_TEST": AI_DS})
    rec = log_prompt(
        prompt="Sinh hệ số",
        response='{"e": -1.2}',
        purpose="elasticity",
        dataset_id="AI_PARAMS_TEST",
        model="claude-x",
        data_dir=tmp_path,
    )
    assert (tmp_path / rec["response_path"]).read_text(encoding="utf-8") == '{"e": -1.2}'
    assert read_prompt_log(tmp_path) == [rec]
    reg = load_registry(tmp_path)
    assert rec["id"] in reg["AI_PARAMS_TEST"].prompt_ids and not reg["GEN_PROGRAM_V1"].prompt_ids
    assert "sinh bởi AI" in label_vi("AI_PARAMS_TEST", reg)
    assert describe("AI_PARAMS_TEST", reg, tmp_path)["prompts"][0]["prompt"] == "Sinh hệ số"


def test_llm_generate_without_key_raises_vietnamese_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    write_registry(tmp_path, {"AI_PARAMS_TEST": AI_DS})
    with pytest.raises(LLMGenerationError) as ei:
        llm_generate("x", "test", "AI_PARAMS_TEST", data_dir=tmp_path)
    assert "ANTHROPIC_API_KEY" in ei.value.message_vi and "kịch bản" not in ei.value.message_vi
    assert read_prompt_log(tmp_path) == []


def test_llm_generate_logs_with_fake_llm(tmp_path):
    seen = []

    def fake(params):
        seen.append(params)
        return LLMResult("kết quả", "claude-fake", "end_turn", {"input_tokens": 3, "output_tokens": 2}, "req_1")

    with pytest.raises(LLMGenerationError):  # dataset not registered as ai_generated
        llm_generate("prompt A", "purpose B", "AI_PARAMS_TEST", data_dir=tmp_path, llm=fake)
    assert not seen
    write_registry(tmp_path, {"AI_PARAMS_TEST": AI_DS})
    gen = llm_generate(
        "prompt A", "purpose B", "AI_PARAMS_TEST", "claude-fake", data_dir=tmp_path, llm=fake,
        params={"max_tokens": 100, "output_config": {"effort": "low"}}, task="t", attempt=2,
    )
    assert gen.text == "kết quả" and gen.accepted
    (req,) = seen
    assert req["model"] == "claude-fake" and req["max_tokens"] == 100 and "tools" not in req
    assert req["messages"] == [{"role": "user", "content": "prompt A"}]
    (rec,) = read_prompt_log(tmp_path)
    assert rec["model"] == "claude-fake" and rec["dataset_id"] == "AI_PARAMS_TEST" and rec["task"] == "t"
    assert rec["attempt"] == 2 and rec["status"] == "accepted" and rec["request_id"] == "req_1"
    assert rec["usage"] == {"input_tokens": 3, "output_tokens": 2}
    assert rec["parameters"] == {"model": "claude-fake", "max_tokens": 100, "output_config": {"effort": "low"}}
    assert rec["system"] and rec["prompt"] == "prompt A"
    full = get_prompt(rec["id"], tmp_path)
    assert full["response"] == "kết quả" and full["response_sha256_ok"] is True
    with pytest.raises(KeyError):
        get_prompt("P-nope", tmp_path)


def test_llm_generate_logs_invalid_truncated_and_api_errors(tmp_path):
    write_registry(tmp_path, {"AI_PARAMS_TEST": AI_DS})
    replies = iter([LLMResult("{", "m", "end_turn"), LLMResult('{"a"', "m", "max_tokens")])
    gen = llm_generate("p", "x", "AI_PARAMS_TEST", data_dir=tmp_path, llm=lambda _: next(replies),
                       validate=lambda text: None if text == "{}" else "không phải {}")
    assert not gen.accepted and gen.record["error"] == "không phải {}"
    gen = llm_generate("p", "x", "AI_PARAMS_TEST", data_dir=tmp_path, llm=lambda _: next(replies))
    assert gen.record["status"] == "invalid" and "max_tokens" in gen.record["error"]

    def broken(_):
        raise LLMGenerationError("Dịch vụ AI trả lỗi (mã 500): lỗi")

    with pytest.raises(LLMGenerationError) as ei:
        llm_generate("p", "x", "AI_PARAMS_TEST", data_dir=tmp_path, llm=broken)
    assert ei.value.record["status"] == "api_error" and ei.value.record["response_path"] is None
    assert [r["status"] for r in read_prompt_log(tmp_path)] == ["invalid", "invalid", "api_error"]
    assert len({r["id"] for r in read_prompt_log(tmp_path)}) == 3


def test_secrets_are_redacted_from_the_log(tmp_path):
    write_registry(tmp_path, {"AI_PARAMS_TEST": AI_DS})
    fake_key = "sk-ant-" + "api03-" + "x" * 20
    llm_generate(f"key {fake_key}", "x", "AI_PARAMS_TEST", data_dir=tmp_path,
                 llm=lambda _: LLMResult(f"echo {fake_key}", "m", "end_turn"), params={"metadata": fake_key})
    for path in (tmp_path / "provenance").rglob("*"):
        if path.is_file():
            assert "sk-ant" not in path.read_text(encoding="utf-8"), path


def test_prompt_cli(tmp_path, capsys):
    write_registry(tmp_path, {"AI_PARAMS_TEST": AI_DS})
    gen = llm_generate("Câu hỏi đầy đủ", "x", "AI_PARAMS_TEST", data_dir=tmp_path, task="demo",
                       llm=lambda _: LLMResult('{"ok": 1}', "claude-haiku-5-5", "end_turn"))
    assert main(["--data-dir", str(tmp_path), "prompts"]) == 0
    out = capsys.readouterr().out
    assert gen.record["id"] in out and "task=demo" in out and "claude-haiku-5-5" in out and "accepted" in out
    assert main(["--data-dir", str(tmp_path), "prompt", gen.record["id"]]) == 0
    out = capsys.readouterr().out
    assert "Câu hỏi đầy đủ" in out and '{"ok": 1}' in out and "===== RESPONSE =====" in out
    (tmp_path / gen.record["response_path"]).write_text("sửa tay", encoding="utf-8")
    assert main(["--data-dir", str(tmp_path), "prompt", gen.record["id"]]) == 1
    assert main(["--data-dir", str(tmp_path), "prompt", "P-nope"]) == 1


def test_manifest_and_cli(tmp_path, capsys):
    raw = tmp_path / "raw" / "x.json"
    raw.parent.mkdir()
    raw.write_text("{}")
    entry = record_raw_file(
        tmp_path,
        raw,
        url="https://example.org",
        retrieved_at="2026-10-13T00:00:00Z",
        license="ODbL 1.0",
        dataset_id="OSM_HCMC",
    )
    assert entry["path"] == "raw/x.json" and entry["bytes"] == 2
    assert verify_manifest(tmp_path) == [("raw/x.json", "ok")]
    assert main(["--data-dir", str(tmp_path), "verify"]) == 0
    raw.write_text("{} ")
    assert main(["--data-dir", str(tmp_path), "verify"]) == 1
    assert main(["--data-dir", str(tmp_path), "show"]) == 0
    assert main(["--data-dir", str(tmp_path), "show", "OSM_HCMC"]) == 0
    out = capsys.readouterr().out
    assert "OSM_HCMC" in out and "GEN_PROGRAM_V1" in out
    assert json.loads(out[out.index("{") :])["license"] == "ODbL 1.0"
