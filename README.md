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

## Chạy toàn bộ hệ thống

Toàn bộ dữ liệu là **giả lập** (SIMULATED); xem tab "Giả định dữ liệu" hoặc `docs/data-assumptions.md`.

```bash
# 0. Phụ thuộc
git submodule update --init && uv sync
(cd web && npm install)

# 1. Solver PACO (routing-PL) trong Docker — cổng lấy từ .env (FRESHMESH_SOLVER_PORT, ví dụ 8001)
docker compose up -d --build solver
curl -s localhost:8001/health          # {"status":"ok"}

# 2. Dữ liệu + mô hình: sinh 3 chuỗi (seed 42) → huấn luyện dự báo cục bộ → học liên kết (FL)
scripts/bootstrap.sh                   # thêm --skip-fl để bỏ bước FL (khi đó /api/network/fl trả 503 fl_not_ready)

# 3. API FastAPI ở cổng 8100 (FRESHMESH_API_PORT)
FRESHMESH_SECRET=$(openssl rand -hex 32) scripts/dev_api.sh   # bỏ biến này: dev_api.sh dùng khóa dev và chỉ nghe 127.0.0.1
curl -s localhost:8100/api/health      # {"status":"ok","solver":true,"llm":false,"mode":"scripted",...}

# 4. Web Next.js ở cổng 3100 (proxy /api/* → 8100)
(cd web && npm run dev)                # mở http://localhost:3100, đăng nhập owner_a / demo123
# Bản production: (cd web && npm run build && npm run start) — mặc định chỉ nghe 127.0.0.1 (đặt HOST=0.0.0.0 để mở ra LAN,
# khi đó BẮT BUỘC dùng FRESHMESH_SECRET ngẫu nhiên cho API, không dùng khóa dev).

# 5. Luồng 1 bằng CLI (cùng tầng dịch vụ với API)
uv run python -m decision.cli flow1 --chain CHAIN_A --store A-CH1 --items rau,thit

# 6. Kiểm thử
uv run pytest                          # unit + API (dữ liệu tạm, solver giả, không cần Docker)
uv run pytest -m integration           # cần container solver (lộ trình PACO thật)
uv run ruff check
(cd web && npx playwright install chromium && npm run test:e2e)   # cần API + web đang chạy
```

Tài khoản demo (mật khẩu `demo123`): `owner_a`, `owner_b`, `owner_c` (chủ chuỗi, xem mọi cửa hàng) và
`manager_a1`, `manager_b1`, `manager_c1` (quản lý cửa hàng CH1, chỉ thao tác trên cửa hàng của mình).

Biến môi trường của API:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `FRESHMESH_API_PORT` | `8100` | cổng API (`scripts/dev_api.sh`) |
| `FRESHMESH_DATA_DIR` | `data` | thư mục dữ liệu (DB chuỗi, mô hình, cache) |
| `FRESHMESH_SECRET` | **bắt buộc** (≥ 32 ký tự) | khóa ký token HS256; thiếu thì API không khởi động |
| `FRESHMESH_ALLOW_DEV_SECRET` | (trống) | `1` = cho phép khóa dev cục bộ (chỉ dùng khi phát triển) |
| `FRESHMESH_ENABLE_DOCS` | (trống) | `1` = bật `/docs` và `/openapi.json` |
| `FRESHMESH_TOKEN_TTL_S` | `28800` | thời hạn token (giây) |
| `FRESHMESH_SOLVER_URL` | từ `.env` | địa chỉ container solver |
| `FRESHMESH_WARM_CACHE` | `1` | `0` để tắt việc tính sẵn lộ trình khi khởi động |
| `FRESHMESH_CACHE_DIR` | `data/cache` | nơi lưu cache lộ trình (JSON theo hash đợt đơn) |
| `ANTHROPIC_API_KEY` | (trống) | có khóa thì chat dùng LLM; không có thì chế độ kịch bản |

- **Không có `ANTHROPIC_API_KEY`**: `/api/health` báo `mode: "scripted"`; chat ở chế độ kịch bản nhận diện 3 câu lệnh
  tiếng Việt (nhập hàng / còn nhiều hàng / gom đơn giao), gọi công cụ thật trên dữ liệu thật. Chọn `mode: "llm"` sẽ trả lỗi
  `llm_unavailable` bằng tiếng Việt.
- **Lộ trình PACO**: một đợt 30–40 đơn mất khoảng 8–25 giây khi giải lần đầu. Khi API khởi động, một luồng nền tính sẵn
  đợt giao của CH1 (luồng 3) và chuyến điều chuyển từ CH3 (luồng 2) cho cả 3 chuỗi; kết quả lưu theo hash đợt đơn trong
  `data/cache/routing/` nên các lần sau (kể cả sau khi khởi động lại) gần như tức thì. Solver lỗi → API trả lỗi tiếng Việt,
  không bao giờ tạo lộ trình giả.
- **Duyệt là đường thực thi duy nhất**: agent và nút bấm chỉ tạo bản nháp; `POST /api/drafts/{id}/approve` mới tạo đơn đặt
  hàng / lịch giảm giá / phiếu điều chuyển / đánh dấu gửi lộ trình (giả lập) và ghi nhật ký quyết định.
- Hợp đồng API và các điểm bổ sung: `docs/api-contract-notes.md`.

## Giới hạn đã biết

- **Chưa chạy với LLM thật**: môi trường phát triển không có `ANTHROPIC_API_KEY`. Đường LLM (`agent/llm.py`) mới có
  test đơn vị và bộ eval chạy bằng client giả; luồng demo chạy bằng chế độ kịch bản với công cụ thật.
- **Học liên kết**: FL tốt hơn Local ở cửa hàng mới nhưng không tốt hơn ở mức tổng thể, và phần lợi ở cửa hàng mới
  chưa chắc do việc liên kết (xem `docs/experiments/fl-results.md`). Mô hình FL triển khai không bật DP.
- **Mô phỏng 30 ngày**: cấu hình đăng ký trước (v1) không đạt tiêu chí hàng bỏ; bản điều chỉnh v2 (chi phí giữ qua đêm
  20% cho hàng tươi) đạt và đang là mặc định, nhưng là điều chỉnh sau khi biết kết quả
  (xem `docs/experiments/sim30-results.md`).
- **Benchmark solver**: solver SA của routing-PL lỗi trên instance của FreshMesh nên không có số SA (xem
  `docs/experiments/routing-benchmark.md`).
- **Phụ thuộc**: `flwr` 1.39 ghim `cryptography<47`, nên môi trường giữ `cryptography` 46.x có cảnh báo bảo mật đã biết.
  `flwr` chỉ được dùng ở `forecasting/fl`; API không nạp nó lúc khởi động, nhưng sẽ nạp khi có yêu cầu đến
  `/api/network/fl` (gói `forecasting.fl` import `flwr`).
- **BLAS**: `forecasting/__init__.py` ghim numpy dùng 1 luồng (mô hình nhỏ; 16 luồng chậm hơn ~13 lần).
- **`query_data` và kiểm tra số**: mọi số trong kết quả truy vấn là số do DB tính từ dữ liệu thật; bộ lọc chặn hằng số, `LIMIT`
  lồng nhau và chuỗi trong danh sách cột để model không "đúc" số tùy ý, nhưng không chặn được phép tính trên cột thật
  (ví dụ `length(sku_id)*length(sku_id)`): đó là rủi ro còn lại, chỉ ảnh hưởng chế độ LLM (chưa bật trong demo).
- **Dữ liệu**: toàn bộ dữ liệu là giả lập (SIMULATED) — xem `docs/data-assumptions.md` cho lộ trình sang dữ liệu thật.
