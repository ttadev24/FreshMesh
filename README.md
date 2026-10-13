# FreshMesh

Nền tảng hỗ trợ quyết định nhập hàng tươi và giao hàng cho mạng lưới chuỗi mini-mart độc lập: dự báo nhu cầu học liên kết, tối ưu lộ trình PACO (VRP có tủ nhận hàng) và AI agent tiếng Việt.

Thiết kế: [docs/superpowers/specs/2026-10-12-freshmesh-design.md](docs/superpowers/specs/2026-10-12-freshmesh-design.md)

## Chạy adapter định tuyến (PACO)

```bash
git submodule update --init          # lấy routing-PL
uv sync
docker compose up -d --build solver  # container solver ở cổng 8000 (hoặc cổng cấu hình trong .env)
uv run python -m routing.cli routing/examples/batch_q7.json
uv run pytest                        # unit test (không cần Docker)
uv run pytest -m integration         # cần container solver
```

Dữ liệu trong `routing/examples/` là **giả lập** (SIMULATED).
