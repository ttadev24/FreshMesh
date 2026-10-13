import argparse
import json
from pathlib import Path

from provenance import describe, label_vi, load_registry, read_manifest, read_prompt_log, verify_manifest


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m provenance", description="FreshMesh data provenance")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    show = sub.add_parser("show", help="list datasets, or show one dataset in full")
    show.add_argument("dataset_id", nargs="?")
    sub.add_parser("verify", help="re-hash every raw file listed in the manifest")
    args = parser.parse_args(argv)
    if args.cmd == "show":
        return _show(args.data_dir, args.dataset_id)
    return _verify(args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
