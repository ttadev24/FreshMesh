import argparse
import datetime as dt
import json
from pathlib import Path

SOURCES = ("osm", "weather", "nso", "osrm")


def fetch(data_dir: Path, only: list[str], today: dt.date, pairs: int, refresh: bool = False) -> int:
    # Lazy: osrm/data_sim load the AI parameter files, which `generate-params` must be able to create.
    from data_real import nso, osm, osrm, snapshot, weather
    from data_real.net import FetchError, PoliteClient
    from data_sim.assumptions import SIM_AS_OF
    from data_sim.generate import WEATHER_FUTURE_DAYS
    from provenance import write_registry

    client = PoliteClient()
    failed: list[str] = []
    try:
        for name in only:
            print(f"[{name}]")
            try:
                if name == "osm":
                    osm.fetch_osm(data_dir, snapshot.OSM_PATH, refresh=refresh)
                elif name == "weather":
                    need = SIM_AS_OF + dt.timedelta(days=WEATHER_FUTURE_DAYS)
                    weather.fetch_weather(
                        data_dir, client, snapshot.WEATHER_PATH, today=today, need_until=need
                    )
                elif name == "nso":
                    nso.fetch_nso(data_dir, client, snapshot.NSO_PATH)
                elif name == "osrm":
                    snapshot.clear_cache()
                    res = osrm.fetch_detour(data_dir, client, snapshot.osm(), snapshot.DETOUR_PATH, n=pairs)
                    print("  " + json.dumps(res["summary"]["all"], ensure_ascii=False))
            except FetchError as exc:
                failed.append(name)
                print(f"  KHÔNG tải được nguồn {name}: {exc}")
    finally:
        client.close()
    snapshot.clear_cache()
    path = write_registry(data_dir, snapshot.registry_updates())
    print(f"Registry: {path}")
    if failed:
        print(f"Nguồn lỗi: {', '.join(failed)} (snapshot cũ, nếu có, được giữ nguyên)")
    return 1 if failed else 0


def generate_params(data_dir: Path, task: str | None, force: bool, model: str | None) -> int:
    from data_real import ai_params
    from provenance import LLMGenerationError

    tasks = [task] if task else list(ai_params.TASKS)
    failed: list[str] = []
    for name in tasks:
        path = ai_params.param_path(name)
        if path.exists() and not force:
            print(f"[{name}] đã có {path} (bỏ qua; dùng --force để sinh lại)")
            continue
        print(f"[{name}] gọi {model or ai_params.DEFAULT_MODEL} …", flush=True)
        try:
            out = ai_params.generate(name, data_dir=data_dir, model=model, force=force)
        except LLMGenerationError as exc:
            failed.append(name)
            print(f"  LỖI: {exc.message_vi}")
            continue
        header = json.loads(out.read_text(encoding="utf-8"))["header"]
        print(f"  -> {out} (prompt {header['prompt_id']}, {len(header['attempt_prompt_ids'])} lần gọi, "
              f"token {header['usage']})")
    log = data_dir / "provenance" / "prompts.jsonl"
    print(f"Nhật ký prompt: {log} (`uv run python -m provenance prompts`)")
    if failed:
        print(f"Tác vụ lỗi: {', '.join(failed)}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m data_real", description="FreshMesh public-data ingestion"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download public sources into data/raw + data_real/snapshot")
    f.add_argument("--data-dir", type=Path, default=Path("data"))
    f.add_argument("--only", default=",".join(SOURCES), help=f"comma list of {SOURCES}")
    f.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    f.add_argument("--pairs", type=int, default=200, help="OSRM detour sample size")
    f.add_argument("--refresh", action="store_true", help="re-download OSM layers even if raw files exist")
    b = sub.add_parser("build", help="build data/chains/*.sqlite from the snapshots (offline)")
    b.add_argument("--out", type=Path, default=Path("data"))
    b.add_argument("--seed", type=int, default=42)
    g = sub.add_parser("generate-params", help="ask Claude for simulation parameters")
    g.add_argument("--data-dir", type=Path, default=Path("data"), help="where the prompt log is written")
    g.add_argument("--task", default=None, help="one task: catalog|demand|chains|orders|elasticity|lots")
    g.add_argument("--force", action="store_true", help="regenerate even if the parameter file exists")
    g.add_argument("--model", default=None, help="model id (default claude-haiku-5-5)")
    args = parser.parse_args(argv)
    if args.cmd == "generate-params":
        from data_real.ai_params import TASKS

        if args.task and args.task not in TASKS:
            parser.error(f"unknown task {args.task!r}; one of {sorted(TASKS)}")
        return generate_params(args.data_dir, args.task, args.force, args.model)
    if args.cmd == "fetch":
        only = [s.strip() for s in args.only.split(",") if s.strip()]
        unknown = set(only) - set(SOURCES)
        if unknown:
            parser.error(f"unknown sources: {sorted(unknown)}")
        return fetch(args.data_dir, only, args.today, args.pairs, args.refresh)
    from data_sim.__main__ import main as build_main

    return build_main(["--out", str(args.out), "--seed", str(args.seed)])


if __name__ == "__main__":
    raise SystemExit(main())
