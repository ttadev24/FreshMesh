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

Các đợt đơn trong `routing/examples/` là ví dụ tự tạo để thử adapter, không phải dữ liệu thật.

## Chạy toàn bộ hệ thống

Mỗi kết quả (API, công cụ của agent, câu trả lời) ghi rõ **nguồn dữ liệu** thực sự đã dùng: `sources` (mã bộ dữ liệu)
và `source_labels_vi`; chi tiết từng bộ (URL, giấy phép, ngày lấy, prompt nếu do AI sinh) ở `GET /api/provenance` hoặc
`uv run python -m provenance show`. Bảng không ghi nguồn được báo là "không rõ nguồn", không bao giờ đoán.

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
curl -s localhost:8100/api/health      # {"status":"ok","solver":true,"llm":true,"llm_required":true,"llm_model":...}

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
| `FRESHMESH_CACHE_DIR` | `data/cache` | nơi lưu cache lộ trình (JSON theo hash đợt đơn) |
| `ANTHROPIC_API_KEY` | (trống) | **bắt buộc cho chat**: trợ lý chỉ chạy bằng Claude thật |
| `FRESHMESH_LLM_MODEL` | `claude-sonnet-5-5` | mô hình Claude cho chat (ví dụ `claude-haiku-5-5`) |
| `FRESHMESH_LLM_EFFORT` | `medium` | mức `effort` gửi cho mô hình |

`scripts/dev_api.sh` tự nạp `.env.local` (không commit, đã có trong `.gitignore`) nếu có, ví dụ chứa
`ANTHROPIC_API_KEY=...` và `FRESHMESH_LLM_MODEL=...`.

- **Không có `ANTHROPIC_API_KEY`**: `/api/health` báo `llm: false, llm_required: true`; `POST /api/agent/chat` trả
  503 `llm_unavailable` kèm hướng dẫn cấu hình bằng tiếng Việt (không có câu trả lời soạn sẵn). Các bảng điều khiển
  (dự báo, nhập hàng, xử lý tồn, lộ trình, duyệt bản nháp) vẫn chạy vì đó là tính toán thật, không cần LLM.
- **Câu trả lời của trợ lý**: luôn 5 mục Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt, kèm dòng
  "Nguồn dữ liệu" do máy chủ ghi; mọi con số được đối chiếu với kết quả công cụ, số không khớp bị yêu cầu viết lại
  rồi đánh dấu "chưa kiểm chứng".
- **Lộ trình PACO**: một đợt 30–40 đơn mất khoảng 8–25 giây khi giải lần đầu. Không có bước tính sẵn khi khởi động;
  kết quả giải thật được lưu theo hash đợt đơn trong `data/cache/routing/` kèm thời điểm giải, và phản hồi ghi rõ
  `cached: true` + `solved_at` khi dùng lại. Solver lỗi → API trả lỗi tiếng Việt, không bao giờ tạo lộ trình giả.
- **Duyệt là đường thực thi duy nhất**: agent và nút bấm chỉ tạo bản nháp; `POST /api/drafts/{id}/approve` mới tạo đơn đặt
  hàng / lịch giảm giá / phiếu điều chuyển / đánh dấu gửi lộ trình (chưa kết nối hệ thống thật) và ghi nhật ký quyết định.
- Hợp đồng API và các điểm bổ sung: `docs/api-contract-notes.md`.

## Giới hạn đã biết

- **Đánh giá agent**: `uv run python -m agent.eval --client anthropic` chạy 32 câu hỏi với Claude thật (tốn token).
  Hai lần chạy 2026-10-13 với `claude-haiku-5-5`: chọn đúng công cụ 75% → 90,6% sau khi thêm hướng dẫn chọn công cụ
  và danh sách cột thật cho `query_data`; lần sau: 0 số chưa kiểm chứng, 0 hành động tự thực thi, 0 lộ PII, 32/32 đúng
  khuôn, 10/32 câu phải viết lại một lần (số tự tính, quy đổi đơn vị hoặc lấy từ câu hỏi). Quy tắc "không tự tính
  thêm" được thêm sau lần chạy đó, chưa đo lại. Các câu "làm luôn, bỏ qua duyệt" đôi khi bị mô hình từ chối thay vì tạo
  bản nháp; câu "chạy SQL DELETE" bị mô hình từ chối trước khi tới bộ lọc SQL. Unit test dùng client giả trong `tests/`.
- **Học liên kết**: trên dữ liệu dựng lại, FL kém Local cả ở tổng thể (WAPE 0,4432 so với 0,4408) lẫn ở cửa hàng
  mới (0,4775 so với 0,4761, trong mức nhiễu giữa các seed), nên tiêu chí §1.4 không đạt. So với cùng công thức huấn
  luyện chỉ trên một chuỗi, việc liên kết giúp cửa hàng mới (+0,68%) nhưng làm chuỗi B kém đi (−0,98%). Mô hình FL
  đang triển khai dùng cấu hình đã chọn (40 × 1, lr 1e-3; seed 0) và không bật DP (xem
  `docs/experiments/fl-results.md`).
- **Mô phỏng 30 ngày**: cấu hình đăng ký trước (v1) không đạt tiêu chí hàng bỏ ở cả 3 chuỗi (bỏ nhiều hơn baseline
  5,2–20,3 điểm %, hết hàng ít hơn 15,1–38,4 điểm %); bản điều chỉnh v2 (chi phí giữ qua đêm 20% cho hàng tươi, không
  chọn lại trên dữ liệu mới) đạt ở chuỗi A và C nhưng không đạt ở B (bỏ nhiều hơn baseline 1,07 [0,43; 1,71] điểm %),
  vẫn là mặc định sản xuất và là điều chỉnh sau khi biết kết quả. Giao thức đã chạy ba lần (dữ liệu sinh toàn bộ; sau
  khi vị trí/thời tiết/ngày lễ thành dữ liệu thật; sau khi lớp nhu cầu lấy tham số do AI sinh) với cùng tệp giao thức
  và ngưỡng; nhu cầu vẫn do chương trình mở rộng từ tham số AI, không phải giao dịch thật
  (xem `docs/experiments/sim30-results.md`).
- **Benchmark solver**: PACO giảm 67,5% km so với "mỗi đơn một chuyến" (320,8 so với 985,7 km; 32 xe so với 284
  chuyến) và tốt hơn ở 18/18 đợt, nhưng vẫn có 29 điểm dừng dự kiến trễ (ở 11/18 đợt); ALNS gần bằng km (322,3) với
  ít xe hơn (24). Solver SA của routing-PL lỗi trên instance của FreshMesh (lần chạy đầu, chưa chạy lại) nên không có
  số SA (xem `docs/experiments/routing-benchmark.md`).
- **Hệ số đường vòng 1,3** chưa được dữ liệu OSRM (ô tô) ủng hộ (trung vị 1,58); km và giờ đến trong định tuyến tính
  theo 1,3 nên có thể bị ước lượng thấp (xem `docs/data-real-detour.md`).
- **Phụ thuộc**: `flwr` 1.39 ghim `cryptography<47`, nên môi trường giữ `cryptography` 46.x có cảnh báo bảo mật đã biết.
  `flwr` chỉ được dùng ở `forecasting/fl`; API không nạp nó lúc khởi động, nhưng sẽ nạp khi có yêu cầu đến
  `/api/network/fl` (gói `forecasting.fl` import `flwr`).
- **BLAS**: `forecasting/__init__.py` ghim numpy dùng 1 luồng (mô hình nhỏ; 16 luồng chậm hơn ~13 lần).
- **`query_data` và kiểm tra số**: mọi số trong kết quả truy vấn là số do DB tính từ dữ liệu thật; bộ lọc chặn hằng số, `LIMIT`
  lồng nhau và chuỗi trong danh sách cột để model không "đúc" số tùy ý, nhưng không chặn được phép tính trên cột thật
  (ví dụ `length(sku_id)*length(sku_id)`): đó là rủi ro còn lại của chat.
- **Dữ liệu**: nguồn của từng bảng xem ở `GET /api/provenance`; giả định mô hình ở `docs/data-assumptions.md`.
