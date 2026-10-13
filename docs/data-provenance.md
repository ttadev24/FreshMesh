# Nguồn gốc dữ liệu FreshMesh

Mọi con số hiển thị cho người dùng đều mang **mã nguồn dữ liệu** (dataset id) thay cho nhãn chung "SIMULATED".
Mã nguồn nằm trong cột `source` của từng dòng ở DB chuỗi, hoặc trong bảng `data_sources` đối với các cột không
có `source` riêng (thời tiết, lịch, `daily_sales.rain_mm`, tọa độ). Danh mục nguồn: `provenance/registry_defaults.json`
(cam kết trong repo) và `data/provenance/registry.json` (do pipeline ghi, thêm thời điểm lấy dữ liệu và số lượng).

## Kết luận ngắn

- **Dữ liệu thật, công khai**: vị trí cửa hàng, điểm nhận và điểm giao (OpenStreetMap); lượng mưa ngày
  TP.HCM (Open-Meteo); ngày nghỉ lễ (văn bản pháp luật) và âm lịch.
- **Do chương trình sinh** (`GEN_PROGRAM_V1`): doanh số ngày theo cửa hàng–mặt hàng, giá, khuyến mãi,
  tồn kho theo lô, đơn online (thời điểm, số lượng, khung giờ, hình thức nhận), tên chuỗi, tài khoản demo.
  Việt Nam **không có** bộ dữ liệu công khai về doanh số cấp cửa hàng–mặt hàng, nên các lớp này là mô phỏng
  có tham số giả định (`docs/data-assumptions.md`). **Đây không phải số liệu kinh doanh thật.**
- **Do AI sinh**: hiện **không có**. Công cụ `provenance.llm_generate` đã sẵn sàng nhưng chưa chạy vì chưa có
  `ANTHROPIC_API_KEY` (xem mục "Dữ liệu do AI sinh").

## Danh mục nguồn

| Mã | Loại | Nguồn (URL) | Giấy phép | Lấy lúc (UTC) | Dùng vào đâu | Giới hạn |
|---|---|---|---|---|---|---|
| `OSM_HCMC` | public | Overpass API (`overpass-api.de`, `overpass.private.coffee`) trên dữ liệu https://www.openstreetmap.org | ODbL 1.0, ghi công "© OpenStreetMap contributors" | 2026-10-13 07:33–07:42 | Tọa độ cửa hàng, sảnh chung cư (điểm nhận), tòa nhà làm điểm giao; tên phường cho tên cửa hàng; chợ và văn phòng để suy ra loại khu vực | Dữ liệu cộng đồng, có thể thiếu/lỗi thời; ô tòa nhà tây-bắc lấy từ `overpass.private.coffee` có mốc dữ liệu OSM 2026-05-31, các phần khác mốc 2026-10-13 |
| `OSM_HCMC_SITES` | derived | Dẫn xuất từ `OSM_HCMC` | ODbL 1.0 (CSDL dẫn xuất) | như trên | Cột `source` của `stores`, `pickup_points` | Vị trí là thật; việc gán vào chuỗi A/B/C, mã cửa hàng, ngày mở cửa là của chương trình |
| `WEATHER_OPENMETEO_ARCHIVE` | public | https://archive-api.open-meteo.com/v1/archive (tài liệu: https://open-meteo.com/en/docs/historical-weather-api) | CC BY 4.0; API miễn phí **chỉ cho mục đích phi thương mại** (https://open-meteo.com/en/terms) | 2026-10-13 07:14 | Bảng `weather` (2025-10-01 → 2026-10-12) và `daily_sales.rain_mm`; hệ số mưa trong mô hình doanh số | Số liệu tái phân tích/mô hình phân tích tại 10,78°N 106,70°E, không phải số đo trạm; vài ngày cuối là sơ bộ |
| `WEATHER_OPENMETEO_FORECAST` | public | https://api.open-meteo.com/v1/forecast | như trên | 2026-10-13 07:14 | Bảng `weather` 2026-10-13 và 2026-10-14 (ngày API lưu trữ chưa có) | Là **dự báo**, không phải quan trắc |
| `CALENDAR_VN` | public | Bộ luật Lao động 2019 Điều 112; Thông báo 6150/TB-BLĐTBXH (2025); thông báo của Bộ Nội vụ về Tết Bính Ngọ và 9441/TB-BNV (2026); Nghị quyết 28/2026/QH16 (24/11) — đường dẫn trong `data_real/holidays_vn.json` | Văn bản pháp luật không thuộc đối tượng bảo hộ quyền tác giả (Luật SHTT Điều 15); âm lịch tính bằng `lunardate` (GPL-3.0-or-later) | đối chiếu 2026-10-13 | Bảng `calendar` (`is_holiday`, ngày âm, Tết, rằm, mùng 1) | Chỉ có dữ liệu năm 2025–2026; năm khác báo lỗi thay vì đoán. Ngày hoán đổi của khu vực công ghi riêng, không tính là ngày lễ |
| `OSRM_DETOUR_HCMC` | derived | https://router.project-osrm.org (hồ sơ ô tô), chính sách: https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server | Kết quả dẫn xuất từ OSM (ODbL); máy chủ demo phi thương mại, ≤ 1 yêu cầu/giây | 2026-10-13 07:46 | Chỉ để kiểm tra giả định `detour_factor` — xem `docs/data-real-detour.md`; không ghi vào DB | Hồ sơ ô tô, thiên cao so với xe máy |
| `NSO_HCMC_RETAIL_REF` | public | https://huggingface.co/datasets/letrinhan/vn-provinces-trade-tourism-transport-master (tổng hợp từ niên giám NSO/GSO) | Thẻ dữ liệu ghi `other`, **không nêu điều khoản**; số liệu gốc là thống kê công bố của Cục Thống kê | 2026-10-13 07:14 | Chỉ làm mốc so sánh độ lớn (mục dưới); không ghi vào DB, không chỉnh tham số | Bảng nguồn không ghi đơn vị; theo quy ước niên giám là tỷ đồng giá hiện hành; địa giới TP.HCM cũ (trước sáp nhập 2025) |
| `GEN_PROGRAM_V1` | synthetic_code | Mã nguồn `data_sim/` (seed cố định, mặc định 42) | Mã nguồn dự án | — | `chains`, `skus`, `daily_sales`, `inventory_lots`, `online_orders`, `assumptions`, `users` | Tham số giả định, chưa hiệu chỉnh bằng dữ liệu bán hàng thật |

## Mã nguồn theo bảng của DB chuỗi

| Bảng | `source` của dòng | Thêm từ `data_sources` |
|---|---|---|
| `stores` | `OSM_HCMC_SITES` | `OSM_HCMC` (lat, lng, name) |
| `pickup_points` | `OSM_HCMC_SITES` | `OSM_HCMC` (lat, lng, name) |
| `online_orders` | `GEN_PROGRAM_V1` | `OSM_HCMC` (lat, lng = tâm một tòa nhà ở thật) |
| `daily_sales` | `GEN_PROGRAM_V1` | `WEATHER_OPENMETEO_ARCHIVE` (rain_mm) |
| `weather` | — | `WEATHER_OPENMETEO_ARCHIVE`, `WEATHER_OPENMETEO_FORECAST` |
| `calendar` | — | `CALENDAR_VN` |
| `chains`, `skus`, `inventory_lots`, `assumptions` | `GEN_PROGRAM_V1` | — |
| `drafts` | mặc định `GEN_PROGRAM_V1` (API có thể ghi giá trị khác) | — |

Bảng `osm_refs(table_name, row_id, osm_id, dataset_id)` giữ phần tử OSM gốc (ví dụ `node/5864095091`) của từng
cửa hàng, điểm nhận và điểm giao. Tên/thương hiệu thật của cửa hàng OSM **không** được dùng: cửa hàng được gọi
`CH<n> <tên phường>`, với tên phường là nút `place=suburb` gần nhất trong OSM (tên phường mới sau sắp xếp 2025).
Trong code: `provenance.sources_for(con, ["stores"])` → `["OSM_HCMC_SITES", "OSM_HCMC"]`;
`provenance.label_vi(id)` cho nhãn ngắn; `provenance.describe(id)` cho đầy đủ chi tiết.

## Đã tải được gì (2026-10-13)

- **OSM** (khung vĩ độ 10,70–10,86, kinh độ 106,60–106,82): 1.185 cửa hàng tiện lợi/siêu thị mini, 5.908 tòa
  nhà ở (3.816 house, 1.398 apartments, 558 residential, 136 terrace), 174 chợ, 1.070 văn phòng, 2.176 địa danh.
  Máy chủ `overpass-api.de` có lúc trả lỗi 504/dispatcher; truy vấn tòa nhà được chia 4 ô (một ô do `overpass.private.coffee` trả lời); tệp thô giữ nguyên trong `data/raw/osm/`.
- **Thời tiết**: 420 ngày lưu trữ (2025-08-19 → 2026-10-12, không thiếu ngày nào) + 2 ngày dự báo
  (2026-10-13, 2026-10-14). Mùa khô 2026 (tháng 1–4) trung bình 0,2–2,0 mm/ngày; tháng 9/2026 11,6 mm/ngày.
- **Ngày lễ**: 24 ngày nghỉ (2025–2026) + 3 ngày hoán đổi, mỗi ngày có trích dẫn.
- **OSRM**: 200/200 cặp thành công; trung vị hệ số đường vòng 1,58 (IQR 1,40–1,99).
- **NSO/GSO**: 30 năm (1995–2024) cho TP.HCM.

## So sánh độ lớn với số liệu NSO (chỉ tham khảo)

Năm 2024, tổng mức bán lẻ hàng hóa và doanh thu dịch vụ của TP.HCM (địa giới cũ) là 997.330 (tỷ đồng theo quy
ước niên giám); TP.HCM có 273 siêu thị và 232 chợ. Doanh thu do chương trình sinh cho 18 cửa hàng demo trong
365 ngày là khoảng 65,9 tỷ đồng (trung bình 6,4–15,3 triệu đồng/cửa hàng/ngày tùy chuỗi), tức khoảng 0,007% tổng
mức của thành phố. Hai con số không cùng phạm vi (tổng mức gồm cả dịch vụ, ô tô, xăng dầu…), nên chỉ dùng để
kiểm tra rằng doanh thu mô phỏng ở thang của một cửa hàng nhỏ; **không** có tham số nào được chỉnh theo số này.

## Dữ liệu do AI sinh (khi có khóa API)

- Hàm `provenance.llm_generate(prompt, purpose, dataset_id, model=None)` gọi Claude qua `agent.llm.AnthropicClient`
  (không dùng công cụ), rồi ghi một dòng vào `data/provenance/prompts.jsonl`:
  `id, ts, model, purpose, dataset_id, prompt, prompt_sha256, response_path, response_sha256`; toàn văn câu trả lời
  lưu ở `data/provenance/responses/<id>.txt`.
- Mỗi bộ dữ liệu do AI sinh phải được đăng ký trước với `kind = "ai_generated"` (hàm từ chối ghi nếu mã nguồn
  chưa đăng ký hoặc thuộc loại khác, nên kết quả AI không thể mang nhãn "Mô phỏng bằng chương trình"); `load_registry()` tự gắn các `prompt_ids`
  tương ứng, `describe(id)` trả về toàn bộ prompt. Nhãn hiển thị có chữ "sinh bởi AI, có nhật ký prompt".
- Không có `ANTHROPIC_API_KEY`: hàm dừng với thông báo tiếng Việt và **không ghi gì**. Tính đến 2026-10-13,
  `prompts.jsonl` rỗng — chưa có dữ liệu nào do AI sinh.

## Cách ban tổ chức kiểm tra

**Từ một bản clone repo (không có thư mục `data/`, vì `data/` bị git bỏ qua):**

- Các tệp đã xử lý được cam kết: `data_real/snapshot/osm_hcmc.json`, `weather_hcmc.json`, `osrm_detour.json`,
  `nso_hcmc_retail.json` và `data_real/holidays_vn.json`. Mỗi snapshot có `meta` ghi URL/máy chủ, thời điểm lấy,
  giấy phép và SHA-256 + kích thước của từng phản hồi thô gốc (`raw_sha256` hoặc `raw_files`).
- `uv run python -m data_real build` dựng lại DB và `data/provenance/registry.json` (không cần mạng), sau đó
  `uv run python -m provenance show` liệt kê nguồn.
- Tải lại từ nguồn (`uv run python -m data_real fetch`) rồi so SHA-256 với `meta` để kiểm tra; dữ liệu OSM và vài
  ngày thời tiết gần nhất có thể đã được cập nhật ở nguồn nên SHA-256 có thể khác.

**Trên máy đã chạy `fetch`** (có `data/raw/`, `data/provenance/manifest.json`, `prompts.jsonl`):

```bash
uv run python -m provenance show                 # danh mục nguồn, giấy phép, thời điểm lấy, số prompt AI
uv run python -m provenance show OSM_HCMC        # chi tiết một nguồn (máy chủ, số lượng, mốc dữ liệu OSM)
uv run python -m provenance verify               # băm lại SHA-256 mọi tệp thô trong data/raw/
cat data/provenance/prompts.jsonl                # nhật ký prompt AI (hiện rỗng)
sqlite3 data/chains/CHAIN_A.sqlite "SELECT * FROM data_sources; SELECT * FROM osm_refs LIMIT 5;"
```

Tải lại từ nguồn: `uv run python -m data_real fetch` (mạng; lịch sự: User-Agent định danh FreshMesh, giãn cách
yêu cầu, thử lại có lùi thời gian). Dựng lại DB (không cần mạng, từ các tệp đã cam kết trong
`data_real/snapshot/`): `uv run python -m data_real build` (tương đương `uv run python -m data_sim --out data`).
