import argparse
import json
from pathlib import Path

from provenance import (
    describe,
    get_prompt,
    label_vi,
    load_registry,
    read_manifest,
    read_prompt_log,
    verify_manifest,
)


def _show(data_dir: Path, dataset_id: str | None) -> int:
    reg = load_registry(data_dir)
    if dataset_id:
        try:
            print(json.dumps(describe(dataset_id, reg, data_dir), ensure_ascii=False, indent=2))
        except KeyError as exc:
            print(exc.args[0])
            return 1
        return 0
    print(f"Danh mục nguồn dữ liệu ({len(reg)} bộ):")
    for ds in reg.values():
        print(f"- {ds.id} [{ds.kind}] {label_vi(ds.id, reg)}")
        print(f"    URL: {ds.url or '—'} | Giấy phép: {ds.license or '—'}")
        print(f"    Lấy lúc: {ds.retrieved_at or '—'}")
        if ds.prompt_ids:
            print(f"    Prompt: {', '.join(ds.prompt_ids)}")
    prompts = read_prompt_log(data_dir)
    print(f"Nhật ký prompt AI: {len(prompts)} lượt gọi ({data_dir / 'provenance' / 'prompts.jsonl'})")
    orphans = [p["id"] for p in prompts if p["dataset_id"] not in reg]
    if orphans:
        print(f"CẢNH BÁO: {len(orphans)} prompt gắn với bộ dữ liệu chưa đăng ký: {', '.join(orphans)}")
    print(f"Tệp thô trong manifest: {len(read_manifest(data_dir))}")
    return 0


def _verify(data_dir: Path) -> int:
    results = verify_manifest(data_dir)
    if not results:
        where = data_dir / "provenance" / "manifest.json"
        print(f"Không có manifest tại {where}; chạy `uv run python -m data_real fetch`.")
        return 1
    bad = 0
    for path, status in results:
        print(f"{status:>16}  {path}")
        bad += status != "ok"
    print(f"{len(results) - bad}/{len(results)} tệp khớp SHA-256.")
    return 1 if bad else 0


def _prompts(data_dir: Path) -> int:
    log = read_prompt_log(data_dir)
    print(f"Nhật ký prompt AI: {len(log)} lượt gọi ({data_dir / 'provenance' / 'prompts.jsonl'})")
    for rec in log:
        task = rec.get("task") or rec.get("purpose")
        status = rec.get("status", "accepted")
        print(f"{rec['id']}  task={task}  lần={rec.get('attempt', 1)}  {rec['ts']}  {rec['model']}  {status}")
    return 0


def _prompt(data_dir: Path, prompt_id: str) -> int:
    try:
        rec = get_prompt(prompt_id, data_dir)
    except KeyError as exc:
        print(exc.args[0])
        return 1
    meta = {k: v for k, v in rec.items() if k not in ("system", "prompt", "response")}
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("\n===== SYSTEM =====")
    print(rec.get("system") or "")
    print("\n===== PROMPT =====")
    print(rec["prompt"])
    print("\n===== RESPONSE =====")
    print(rec["response"] if rec["response"] is not None else "(không có câu trả lời — lỗi API)")
    if rec["response_sha256_ok"] is False:
        print("CẢNH BÁO: SHA-256 của câu trả lời không khớp nhật ký.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m provenance", description="FreshMesh data provenance")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    show = sub.add_parser("show", help="list datasets, or show one dataset in full")
    show.add_argument("dataset_id", nargs="?")
    sub.add_parser("verify", help="re-hash every raw file listed in the manifest")
    sub.add_parser("prompts", help="list every logged AI call (id, task, ts, model, status)")
    one = sub.add_parser("prompt", help="print one logged AI call in full (prompt + response)")
    one.add_argument("prompt_id")
    args = parser.parse_args(argv)
    if args.cmd == "show":
        return _show(args.data_dir, args.dataset_id)
    if args.cmd == "prompts":
        return _prompts(args.data_dir)
    if args.cmd == "prompt":
        return _prompt(args.data_dir, args.prompt_id)
    return _verify(args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
