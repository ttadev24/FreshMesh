# Nguồn gốc dữ liệu FreshMesh

Mọi con số hiển thị cho người dùng đều mang **mã nguồn dữ liệu** (dataset id) thay cho nhãn chung "SIMULATED".
Mã nguồn nằm trong cột `source` của từng dòng ở DB chuỗi, hoặc trong bảng `data_sources` đối với các cột không
có `source` riêng (thời tiết, lịch, `daily_sales.rain_mm`, tọa độ). Danh mục nguồn: `provenance/registry_defaults.json`
(cam kết trong repo) và `data/provenance/registry.json` (do pipeline ghi, thêm thời điểm lấy dữ liệu và số lượng).

## Kết luận ngắn

- **Dữ liệu thật, công khai**: vị trí cửa hàng, điểm nhận và điểm giao (OpenStreetMap); lượng mưa ngày
  TP.HCM (Open-Meteo); ngày nghỉ lễ (văn bản pháp luật) và âm lịch.
- **Do AI sinh (tham số)**: danh mục 30 SKU (tên kèm quy cách, giá vốn, giá bán, giá thu hồi, hạn bán, MOQ, nhà cung
  cấp hư cấu), mức nhu cầu nền và các hệ số thứ/lịch âm/lễ/mưa/khuyến mãi, hồ sơ 3 chuỗi, hành vi đơn online, hệ số
  co giãn giá, cơ cấu tuổi lô — 6 bộ `AI_PARAMS_*`, do Claude Haiku 5.5 (`claude-haiku-5-5`) đề xuất ngày 2026-10-14
  qua 6 lượt gọi (cả 6 được chấp nhận ngay lần đầu, không lượt nào lỗi). Toàn văn prompt, câu trả lời, SHA-256, tham
  số gọi và số token đều được lưu và cam kết trong repo (mục "Dữ liệu do AI sinh"). Đây là **ước lượng hợp lý theo
  hiểu biết chung của mô hình, không phải số đo**.
- **Do chương trình sinh từ tham số AI** (`GEN_FROM_AI_PARAMS_V1`): doanh số ngày theo cửa hàng–mặt hàng, khuyến mãi,
  tồn kho theo lô, đơn online (thời điểm, số lượng, khung giờ, hình thức nhận), được `data_sim` mở rộng bằng quá
  trình ngẫu nhiên có seed. Việt Nam **không có** bộ dữ liệu công khai về doanh số cấp cửa hàng–mặt hàng.
  **Đây không phải giao dịch thật.**
- **Do chương trình cố định** (`GEN_PROGRAM_V1`): cơ chế mô phỏng, danh sách nhóm hàng/mặt hàng/`sku_id`, tên và bố
  cục chuỗi, kịch bản demo dư/thiếu rau, tài khoản demo, giả định kinh tế/định tuyến (danh sách đầy đủ ở
  `docs/data-assumptions.md`, mục "Phần vẫn do chương trình cố định").

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
| `AI_PARAMS_CATALOG` | ai_generated | Claude Haiku 5.5, prompt `P20261014T004848-c28383bcd2` → `data_real/generated/catalog.json` | Đầu ra mô hình do nhóm tạo | 2026-10-14 00:48 | Bảng `skus` (giá bán nhân hệ số chuỗi) | Ước lượng, không phải giá khảo sát; giá thu hồi, MOQ, độ phổ biến là phỏng đoán |
| `AI_PARAMS_DEMAND` | ai_generated | prompt `P20261014T004920-fdb3b60047` → `demand.json` | như trên | 2026-10-14 00:49 | Mức nền theo nhóm × khu vực, hệ số thứ/lịch âm/lễ/mưa, khuyến mãi; khóa `promo` của `assumptions` | Phần lớn độ tin cậy thấp |
| `AI_PARAMS_CHAINS` | ai_generated | prompt `P20261014T004938-1a0c646ad5` → `chains.json` | như trên | 2026-10-14 00:49 | Quy mô, độ ưa hàng tươi, độ nhạy, nhiễu, khuyến mãi, hệ số giá, xu hướng của 3 chuỗi | Phỏng đoán từ mô tả định tính tệp khách |
| `AI_PARAMS_ORDERS` | ai_generated | prompt `P20261014T004958-84bbeedddc` → `orders.json` | như trên | 2026-10-14 00:49 | Đơn online; khóa `hourly_sales_share` của `assumptions` | Độ tin cậy thấp |
| `AI_PARAMS_ELASTICITY` | ai_generated | prompt `P20261014T005011-2dcf2d241e` → `elasticity.json` | như trên | 2026-10-14 00:50 | Khóa `markdown_elasticity` của `assumptions` (ra quyết định giảm giá) | Chưa ước lượng từ đợt giảm giá thật |
| `AI_PARAMS_LOTS` | ai_generated | prompt `P20261014T005019-710eedb645` → `lots.json` | như trên | 2026-10-14 00:50 | Cơ cấu lô của `inventory_lots` | Độ tin cậy thấp |
| `GEN_FROM_AI_PARAMS_V1` | derived | `data_sim/` (seed 42) mở rộng từ 6 bộ `AI_PARAMS_*` + `GEN_PROGRAM_V1` + OSM + mưa + lịch | Mã nguồn dự án | — | `daily_sales`, `inventory_lots`, `online_orders` | **Không phải giao dịch thật**; `prompt_ids` = mọi lượt gọi AI tạo tham số cha |
| `GEN_PROGRAM_V1` | synthetic_code | Mã nguồn `data_sim/` (seed cố định, mặc định 42) | Mã nguồn dự án | — | `chains`, `users`, phần lớn khóa của `assumptions`; cơ chế mô phỏng, danh sách SKU, bố cục chuỗi, kịch bản demo | Hằng số của chương trình, không phải số liệu kinh doanh thật |

## Mã nguồn theo bảng của DB chuỗi

| Bảng | `source` của dòng | Thêm từ `data_sources` |
|---|---|---|
| `stores` | `OSM_HCMC_SITES` | `OSM_HCMC` (lat, lng, name) |
| `pickup_points` | `OSM_HCMC_SITES` | `OSM_HCMC` (lat, lng, name) |
| `online_orders` | `GEN_FROM_AI_PARAMS_V1` | `OSM_HCMC` (lat, lng = tâm một tòa nhà ở thật) |
| `daily_sales` | `GEN_FROM_AI_PARAMS_V1` | `WEATHER_OPENMETEO_ARCHIVE` (rain_mm) |
| `inventory_lots` | `GEN_FROM_AI_PARAMS_V1` | — |
| `skus` | `AI_PARAMS_CATALOG` | — |
| `weather` | — | `WEATHER_OPENMETEO_ARCHIVE`, `WEATHER_OPENMETEO_FORECAST` |
| `calendar` | — | `CALENDAR_VN` |
| `chains` | `GEN_PROGRAM_V1` | — |
| `assumptions` | theo khóa: `AI_PARAMS_ELASTICITY`, `AI_PARAMS_ORDERS`, `AI_PARAMS_DEMAND`, còn lại `GEN_PROGRAM_V1` | — |
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
ước niên giám); TP.HCM có 273 siêu thị và 232 chợ. Doanh thu do chương trình sinh (từ tham số AI) cho 18 cửa hàng
demo trong 365 ngày là khoảng 137,7 tỷ đồng (trung bình 11,6–30,1 triệu đồng/cửa hàng/ngày tùy chuỗi), tức khoảng
0,014% tổng mức của thành phố. Hai con số không cùng phạm vi (tổng mức gồm cả dịch vụ, ô tô, xăng dầu…), nên chỉ dùng để
kiểm tra rằng doanh thu mô phỏng ở thang của một cửa hàng nhỏ; **không** có tham số nào được chỉnh theo số này.

## Phần vẫn do chương trình cố định (`GEN_PROGRAM_V1`) và lý do

Không hỏi AI và không có nguồn công khai — là cơ chế/kịch bản của phần mềm, hoặc phải ổn định vì mô-đun khác tham chiếu:

- **Cơ chế mô phỏng**: Negative Binomial, công thức μ, thứ tự rút số ngẫu nhiên và seed (mô-đun `simulation/` phát lại
  đúng quá trình này); lô FIFO; đợt đơn 45 phút; 10 ngày "trước Tết"; ngưỡng mưa 2 mm / 20 mm; chặn dưới 0,3 cho hệ số
  mưa và hệ số thịt/cá ngày rằm; hàng tươi có tần suất khuyến mãi × 0,6; cận dưới khung giờ = thời gian đi + 10 phút.
- **Danh mục 11 nhóm hàng, 30 mặt hàng và `sku_id`**: API, dự báo, demo và kiểm thử tham chiếu tới (AI chỉ đặt tên kèm
  quy cách và các con số).
- **Chuỗi**: tên hư cấu, mô tả tệp khách, số cửa hàng và loại khu vực từng cửa hàng (khớp vị trí OSM), cửa hàng mới;
  ngày mở cửa của cửa hàng đã hoạt động lùi ngẫu nhiên 30–1.500 ngày trước đầu kỳ lịch sử.
- **Kịch bản demo**: dư rau hết hạn ngày mai ở CH3 (2,6–3,4 × bán TB/ngày), thiếu rau ở cửa hàng gần nhất (0,05–0,2 ×);
  mỗi đợt online 12–40 đơn và 1–2 đơn "gấp" có nguy cơ trễ.
- **Tài khoản demo và giả định kinh tế/định tuyến**: mức giảm giá cho phép, phạt hết hàng 0,5 × biên, chi phí điều
  chuyển, tốc độ 20 km/h, hệ số đường vòng 1,3, ca giao 240 phút, bán kính điểm nhận.

## Dữ liệu do AI sinh

**Phạm vi.** AI chỉ sinh **tham số** (6 tệp JSON nhỏ), không sinh từng dòng giao dịch. Từ các tham số này chương
trình `data_sim` sinh doanh số, tồn kho, đơn online bằng quá trình ngẫu nhiên có seed (cố định, tái lập được).

**Các tác vụ** (`data_real/ai_params.py`; mỗi tác vụ = một prompt tiếng Việt + một schema JSON chặt):

| Tác vụ | Mã bộ dữ liệu | Prompt được chấp nhận | Số lần gọi | Token vào / ra |
|---|---|---|---|---|
| `catalog` — 30 SKU: tên + quy cách, giá vốn/bán/thu hồi, hạn bán, MOQ, nhà cung cấp, ô kho lạnh, độ phổ biến | `AI_PARAMS_CATALOG` | `P20261014T004848-c28383bcd2` | 1 | 5.234 / 14.360 |
| `demand` — nền theo nhóm × khu vực; hệ số thứ, mưa, Tết/rằm/mùng 1/lễ, khuyến mãi; phân tán | `AI_PARAMS_DEMAND` | `P20261014T004920-fdb3b60047` | 1 | 6.416 / 3.890 |
| `chains` — hồ sơ hành vi CHAIN_A/B/C | `AI_PARAMS_CHAINS` | `P20261014T004938-1a0c646ad5` | 1 | 3.227 / 2.812 |
| `orders` — theo giờ, số đơn/ngày và/đợt, giỏ 1–3, hình thức nhận, khung giờ, phục vụ, đơn gấp | `AI_PARAMS_ORDERS` | `P20261014T004958-84bbeedddc` | 1 | 5.019 / 3.635 |
| `elasticity` — hệ số co giãn khi giảm giá cận hạn, có khoảng | `AI_PARAMS_ELASTICITY` | `P20261014T005011-2dcf2d241e` | 1 | 2.863 / 1.875 |
| `lots` — tuổi/độ lớn lô tồn cuối ngày | `AI_PARAMS_LOTS` | `P20261014T005019-710eedb645` | 1 | 2.793 / 1.187 |

Tổng: 6 lượt gọi, 0 lượt bị từ chối, 0 lỗi API (ngày 2026-10-14).

**Tham số gọi** (ghi nguyên văn trong từng bản ghi nhật ký): `model = claude-haiku-5-5`, `max_tokens` 16.000–48.000,
`thinking = {"type": "adaptive"}`, `output_config = {"effort": "medium", "format": {"type": "json_schema", "schema":
…}}` (structured outputs: schema đầy đủ nằm trong bản ghi), gọi bằng SDK `anthropic` (streaming). **Không gửi
`temperature`**: Claude Haiku 5.5 chỉ nhận giá trị mặc định 1 (giá trị khác, kể cả 0, bị lỗi 400). Vì vậy gọi lại cùng
prompt có thể cho số khác; tính tái lập dựa trên **câu trả lời đã lưu** (SHA-256), không dựa trên việc gọi lại.

**Prompt yêu cầu**: bối cảnh mini-mart TP.HCM 2026, 3 chuỗi với tệp khách và loại khu vực; với mỗi số phải có
`basis_vi` (lý do), `confidence` (low/medium/high) và `is_guess` (phỏng đoán hay không); `notes_vi` nêu giới hạn;
**cấm bịa nguồn** (không URL, tên miền, tên báo cáo/khảo sát, số thống kê như thể đã tra cứu) và cấm tên thương hiệu
thật; giá trị phải nằm trong khoảng hợp lệ ghi trong prompt.

**Kiểm tra trước khi chấp nhận** (`data_real.ai_params.validate`): đúng schema (pydantic, không thừa/thiếu trường),
khoảng số học và ràng buộc (giá bán > giá vốn > giá thu hồi ≥ 0, hạn bán hàng tươi 1–3 ngày, đủ 30 `sku_id`, tổng tỷ
trọng = 1, hệ số co giãn âm, độ ưa hàng tươi C > A > B, văn phòng vắng cuối tuần …), và quét mọi chuỗi chữ để từ chối
URL/tên miền. Câu trả lời sai được ghi nhật ký với trạng thái `invalid` kèm lỗi, rồi hỏi lại tối đa 3 lần với danh sách
lỗi nối vào cuối prompt; lỗi API ghi trạng thái `api_error`; câu trả lời bị cắt (`max_tokens`) hoặc từ chối
(`refusal`) cũng là `invalid`. Tệp tham số được đọc lại và kiểm tra lại mỗi lần dựng DB; tệp bị sửa tay sai quy tắc sẽ
bị từ chối, và thiếu tệp thì dựng DB dừng với lỗi tiếng Việt (không dùng số mặc định).

**Nhật ký** `data/provenance/prompts.jsonl` (cam kết trong repo): mỗi dòng một lượt gọi —
`id, ts, task, attempt, status (accepted|invalid|api_error), error, model, purpose, dataset_id, system, prompt,
prompt_sha256, parameters (yêu cầu gửi đi, gồm schema), usage (token), stop_reason, request_id, response_path,
response_sha256, parsed_path`. Toàn văn câu trả lời ở `data/provenance/responses/<id>.txt`. Không ghi header, khóa API
hay đối tượng client; mọi chuỗi được lọc mẫu `sk-ant-…` lần nữa trước khi ghi, và kiểm thử khẳng định không có chuỗi
này trong `data/provenance/` và `data_real/generated/`.

**Tệp tham số** `data_real/generated/<task>.json` = `{"header": {...}, "params": {...}}`: `params` **giống hệt** câu
trả lời đã lưu (kiểm thử so `json.loads(response) == params` và SHA-256); `header` ghi mô hình, thời điểm, prompt được
chấp nhận, mọi lượt thử, SHA-256 prompt/câu trả lời/schema, tham số gọi, token và ghi chú về `temperature`.

**Registry**: 6 bộ `AI_PARAMS_*` loại `ai_generated` (nhãn "… do AI đề xuất (sinh bởi AI, có nhật ký prompt)") và bộ
dẫn xuất `GEN_FROM_AI_PARAMS_V1` (nhãn "Sinh bằng chương trình từ tham số do AI (Claude Haiku 5.5) tạo; không phải
giao dịch thật") với `prompt_ids` = hợp của mọi lượt gọi và `details.parents` = các bộ cha. `provenance.describe(id)`
(và API) trả kèm toàn văn các prompt; `provenance.get_prompt(id)` trả một bản ghi kèm câu trả lời và kết quả kiểm tra
SHA-256. Chỉ ghi được nhật ký AI cho bộ dữ liệu đã đăng ký loại `ai_generated`.

**Sinh lại**: `uv run python -m data_real generate-params [--task NAME] [--force]` (cần `ANTHROPIC_API_KEY`; mặc
định bỏ qua tác vụ đã có tệp). Thiếu khóa: dừng với thông báo tiếng Việt và không ghi gì. Sinh lại sẽ thêm dòng mới
vào nhật ký (các dòng cũ giữ nguyên) và thay tệp tham số, nên cần dựng lại DB và huấn luyện lại mô hình.

**Giới hạn**: giá, nhu cầu, hành vi đơn và hệ số co giãn do AI đề xuất là **ước lượng hợp lý, không phải số đo**; mô
hình không truy cập Internet, tự đánh dấu phần lớn số là độ tin cậy thấp/trung bình và nhiều số là phỏng đoán (xem
`basis_vi`, `confidence`, `is_guess`, `notes_vi` trong từng tệp). Không có giao dịch thật nào. Khi có dữ liệu POS thật
(KiotViet/Sapo), các bảng sẽ mang mã nguồn POS và tham số AI chỉ còn là mốc so sánh (`docs/data-assumptions.md`, mục
"Lộ trình chuyển sang dữ liệu thật").

## Cách ban tổ chức kiểm tra

**Từ một bản clone repo (không có thư mục `data/`, vì `data/` bị git bỏ qua):**

- Các tệp đã xử lý được cam kết: `data_real/snapshot/osm_hcmc.json`, `weather_hcmc.json`, `osrm_detour.json`,
  `nso_hcmc_retail.json` và `data_real/holidays_vn.json`. Mỗi snapshot có `meta` ghi URL/máy chủ, thời điểm lấy,
  giấy phép và SHA-256 + kích thước của từng phản hồi thô gốc (`raw_sha256` hoặc `raw_files`).
- Tham số AI: `data_real/generated/*.json`; nhật ký prompt: `data/provenance/prompts.jsonl` và
  `data/provenance/responses/` (thư mục `data/provenance/` được cam kết dù `data/` bị bỏ qua).
- `uv run python -m provenance prompts` liệt kê mọi lượt gọi AI (id, tác vụ, lần, thời điểm, mô hình, trạng thái);
  `uv run python -m provenance prompt <id>` in toàn văn system prompt, prompt, câu trả lời và kiểm tra SHA-256.
- `uv run pytest tests/data_real/test_ai_params.py` kiểm tra: tệp tham số khớp đúng câu trả lời đã lưu, mọi prompt id
  được tham chiếu có trong nhật ký với toàn văn và SHA-256 đúng, không có khóa API trong các tệp cam kết.
- `uv run python -m data_real build` dựng lại DB và `data/provenance/registry.json` (không cần mạng), sau đó
  `uv run python -m provenance show` liệt kê nguồn; `uv run python -m provenance show GEN_FROM_AI_PARAMS_V1` cho các
  bộ cha và toàn văn các prompt.
- Tải lại từ nguồn (`uv run python -m data_real fetch`) rồi so SHA-256 với `meta` để kiểm tra; dữ liệu OSM và vài
  ngày thời tiết gần nhất có thể đã được cập nhật ở nguồn nên SHA-256 có thể khác.

**Trên máy đã chạy `fetch`** (có `data/raw/`, `data/provenance/manifest.json`, `prompts.jsonl`):

```bash
uv run python -m provenance show                 # danh mục nguồn, giấy phép, thời điểm lấy, số prompt AI
uv run python -m provenance show OSM_HCMC        # chi tiết một nguồn (máy chủ, số lượng, mốc dữ liệu OSM)
uv run python -m provenance verify               # băm lại SHA-256 mọi tệp thô trong data/raw/
uv run python -m provenance prompts              # nhật ký prompt AI (6 lượt gọi)
uv run python -m provenance prompt P20261014T004848-c28383bcd2   # toàn văn một lượt gọi
sqlite3 data/chains/CHAIN_A.sqlite "SELECT * FROM data_sources; SELECT * FROM osm_refs LIMIT 5;"
```

Tải lại từ nguồn: `uv run python -m data_real fetch` (mạng; lịch sự: User-Agent định danh FreshMesh, giãn cách
yêu cầu, thử lại có lùi thời gian). Dựng lại DB (không cần mạng, từ các tệp đã cam kết trong
`data_real/snapshot/`): `uv run python -m data_real build` (tương đương `uv run python -m data_sim --out data`).
