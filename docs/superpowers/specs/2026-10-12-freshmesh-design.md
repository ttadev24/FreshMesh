# FreshMesh — Thiết kế

> FreshMesh: nền tảng hỗ trợ quyết định nhập hàng tươi và giao hàng cho mạng lưới chuỗi mini-mart độc lập, dùng dự báo học liên kết, tối ưu lộ trình PACO và AI agent tiếng Việt.
> Bối cảnh: MLAI Hackathon, Decision Intelligence Challenge.

- Ngày: 2026-10-12
- Trạng thái: chờ nhóm review
- Nguồn: đề bài Decision Intelligence Challenge; ý tưởng nhóm; repo bài báo Q1 `chauanphu/routing-PL` (PACO cho VRP-PL)

## 1. Bối cảnh và mục tiêu

### 1.1 Yêu cầu từ đề bài
- Web demo chạy được với ít nhất một luồng hoàn chỉnh: nhập mục tiêu/ràng buộc → phương án → giải thích đánh đổi → hành động tiếp theo.
- Pitch deck: vấn đề, người dùng, luồng, giải pháp, chiến lược dữ liệu, AI, giải thích và kiểm soát rủi ro, mở rộng, tác động.
- Dữ liệu giả lập được phép nhưng phải gắn nhãn, nêu giả định và lộ trình sang dữ liệu thật.
- Quyết định cuối cùng thuộc về con người; phải nêu giả định và độ bất định.
- Thang điểm: Giải quyết vấn đề & tác động 20 · Phù hợp VN 15 · Sáng tạo 20 · Dữ liệu & AI 20 · Khả thi & prototype 15 · Trình bày & UX 10.

### 1.2 Pain point (bằng chứng ngành)
Bách Hóa Xanh chỉ được dùng làm **bằng chứng ngành** trong deck, không phải khách hàng hay đối tác, không dùng logo hay thương hiệu.
- Hàng tươi bị bỏ: VDSC ước tính tỷ lệ bỏ hàng tươi của BHX là 2–3%, khi chuỗi đang thử nghiệm cơ cấu hàng (số liệu khoảng 2019–2020, phải ghi năm trong deck). Từ 2019, chuỗi giảm giá hàng tươi theo khung giờ để kiểm soát hàng hủy.
- Mở rộng giao hàng: doanh thu online BHX năm 2025 được kỳ vọng tăng ≥ 300% (khoảng 2.775 tỷ đồng), với chủ trương giao từ cửa hàng đến khách. Chuỗi mở nhanh, khoảng 1.000 cửa hàng/năm từ 2026.
- Tham chiếu quốc tế (nguồn vendor, dùng thận trọng): hao hụt hàng tươi 5–10%; dự báo nhu cầu giảm 20–30% hao hụt ở nhóm hàng áp dụng.
- Kênh truyền thống (general trade) chiếm phần lớn bán lẻ thực phẩm VN. Các chuỗi mini-mart nhỏ không có đội dữ liệu, đây là thị trường mục tiêu.

Pain point sản phẩm giải quyết:

| # | Pain point | Mô-đun |
|---|---|---|
| 1 | Hàng tươi bị bỏ vì nhập dư | `forecast_demand` + `plan_inventory` (tính hạn sử dụng) |
| 2 | Hết hàng vì nhập thiếu | `plan_inventory` (chi phí hết hàng) |
| 3 | Cửa hàng mới không có lịch sử | Học liên kết (tri thức mạng lưới) |
| 4 | Giảm giá cuối ngày theo cảm tính | `suggest_markdown` |
| 5 | Đơn online giao từ cửa hàng | `optimize_routes` (PACO, gom đơn theo đợt, điểm nhận) |
| 6 | Dư hàng ở cửa hàng này, thiếu ở cửa hàng khác | `transfer_stock` (PACO) |
| 7 | Quản lý không phải chuyên gia dữ liệu | Agent chat tiếng Việt + giải thích + độ tin cậy |

### 1.3 Persona
Chủ hoặc quản lý một **chuỗi mini-mart nhỏ độc lập** (3–15 cửa hàng, ví dụ ở TP.HCM), bán hàng tươi và hàng khô, có đơn online giao từ cửa hàng. Sản phẩm là **nền tảng chung cho nhiều chuỗi như vậy**. Các chuỗi là đối thủ của nhau, không chia sẻ dữ liệu thô, nhưng cùng hưởng mô hình dự báo học liên kết.

### 1.4 Tiêu chí thành công của demo
1. 3 luồng demo chạy trọn trên web (mục 2.3).
2. FL tốt hơn Local-only về WAPE và pinball loss, rõ nhất ở cửa hàng mới.
3. Mô phỏng 30 ngày: % hàng tươi phải bỏ thấp hơn baseline "nhập bằng trung bình 7 ngày" mà % hết hàng không tăng quá ngưỡng nhóm chọn trước khi chạy thí nghiệm, ghi trong `docs/`.
4. PACO tốt hơn baseline "mỗi đơn một chuyến" về tổng km và số xe trên cùng đợt đơn.
5. Bộ đánh giá agent: 0 con số chưa kiểm chứng; 0 hành động tự thực thi.

### 1.5 Ngoài phạm vi
- Tích hợp POS thật (chỉ mô tả lộ trình).
- Định giá động toàn cửa hàng (chỉ làm markdown hàng tươi sắp hết hạn).
- Sửa lõi C++ của PACO (dùng nguyên qua API; khoảng cách đường thật là hướng nâng cấp).
- Ứng dụng mobile cho shipper.

## 2. Kiến trúc tổng thể

### 2.1 Sơ đồ
```
     Chuỗi A        Chuỗi B        Chuỗi C      (mỗi chuỗi = 1 FL client, dữ liệu ở lại)
        └── trọng số ──┴── trọng số ──┘
                       ▼
          FL Server (Flower, FedAvg + FedPer, DP tùy chọn)
                       │ mô hình chung
┌──────────────────────▼──── Workspace của một chuỗi ───────────────────────┐
│ Web UI (Next.js): [Chat Agent] ◄──► [Dashboard theo ngữ cảnh]                   │
│                         │ FastAPI gateway (auth, tenant)                      │
│             Agent điều phối (LLM tool-calling) + guardrail + audit log        │
│  forecast_demand · plan_inventory · suggest_markdown · transfer_stock ·       │
│  optimize_routes · query_data · render_chart                                  │
│  (+ công cụ hành động dạng nháp: create_purchase_order, apply_markdown,       │
│     dispatch_routes — chỉ thực thi khi người dùng bấm Duyệt)                   │
└───────────────────────────────────────────────────────────────────────────────┘
        Dữ liệu giả lập (source = SIMULATED)          routing-PL (container riêng, POST /solve/manual)
```

### 2.2 Nguyên tắc
1. LLM không tự sinh con số; mọi số liệu đến từ công cụ xác định và được dẫn nguồn.
2. Mọi hành động có tác động cần người dùng xác nhận trên UI.
3. Mỗi đề xuất kèm độ tin cậy và giả định.
4. Mọi công cụ chạy và test được không cần LLM; UI có nút bấm thay cho chat.

### 2.3 Luồng demo
1. **Sáng, nhập hàng:** "Nhập rau và thịt cho mai thế nào?" → dự báo P10/P50/P90 → 3 phương án (An toàn / Cân bằng / Tiết kiệm), mỗi phương án có tổng tiền, % hàng bỏ dự kiến, % hết hàng, lý do → duyệt → bản nháp đơn đặt hàng → xác nhận.
2. **Chiều, xử lý tồn:** "Còn nhiều rau ở CH3" → so sánh bằng tiền giữa giảm giá theo khung giờ và điều chuyển sang cửa hàng thiếu (PACO) → duyệt.
3. **Giao online:** mỗi 30–60 phút gom đơn một lần → PACO tính lộ trình, có điểm nhận → bản đồ, km, số xe, đơn có nguy cơ trễ → xác nhận gửi lộ trình.

## 3. Dữ liệu giả lập (`data_sim/`)
- Seed cố định, có thể chạy lại. Mọi bảng có cột `source = 'SIMULATED'`.
- 3–5 chuỗi, mỗi chuỗi 3–15 cửa hàng. Tọa độ lấy từ instance của routing-PL rồi ánh xạ lên khu vực TP.HCM; mỗi cửa hàng gán loại khu vực (dân cư / gần chợ / văn phòng).
- Khoảng 30 SKU mỗi cửa hàng, gồm nhóm tươi (hạn 1–3 ngày) và khô.
- Doanh số ngày = nền × hệ số thứ trong tuần × hệ số lịch âm (Tết, rằm, mùng 1) × hệ số mưa × khuyến mãi × nhiễu (Poisson hoặc NegBin).
- Non-IID giữa các chuỗi: tham số khác nhau theo loại khu vực và tệp khách.
- 1–2 cửa hàng mới chỉ có 14 ngày lịch sử (kịch bản cold-start).
- Đơn online: sinh theo giờ quanh mỗi cửa hàng, gồm vị trí, khung giờ, lựa chọn nhận (tận nhà / điểm nhận / linh hoạt).
- Hệ số co giãn giá cho markdown: tham số giả định, ghi trong `docs/data-assumptions.md`.
- Lộ trình sang dữ liệu thật: xuất từ POS (KiotViet, Sapo) → ánh xạ vào cùng schema; pilot 2–3 mini-mart.

## 4. Dự báo, học liên kết, độ tin cậy (`forecasting/`)

### 4.1 Mô hình
- Mạng neural nhỏ (MLP hoặc GRU) dự báo 3 phân vị P10/P50/P90 bằng pinball loss. Chọn mạng neural vì FedAvg hoạt động trên trọng số.
- Feature: lag 1/7/14, rolling mean/std, thứ, lịch âm và dương, ngày lễ VN, mưa, khuyến mãi, loại khu vực, nhóm hàng, embedding SKU.
- Interface: `forecast_demand(chain_id, store_ids, sku_ids, horizon_days) -> [{store, sku, date, p10, p50, p90, confidence, reason}]`.

### 4.2 Học liên kết
- Flower. Mỗi chuỗi là một client và chỉ gửi trọng số.
- FedPer: thân mô hình học chung, đầu ra fine-tune cục bộ.
- DP tùy chọn: clip gradient + nhiễu Gaussian; báo cáo đường cong ε so với WAPE.
- Secure aggregation tùy chọn (ưu tiên thấp nhất).
- Thí nghiệm bắt buộc: Local-only / FL / Centralized (cận trên, chỉ làm được vì dữ liệu giả lập), báo cáo riêng cho cửa hàng mới.

### 4.3 Độ tin cậy
- Split conformal trên holdout của từng chuỗi, độ phủ mục tiêu 80% (P10–P90).
- Thẻ tin cậy Cao/Trung bình/Thấp dựa trên: độ rộng khoảng tương đối, số ngày lịch sử, độ phủ thực tế 7 ngày gần nhất. Kèm một câu lý do.
- Drift: độ phủ 7 ngày < 70% → cảnh báo và gợi ý chọn phương án An toàn.

## 5. Ra quyết định (`decision/`)

### 5.1 `plan_inventory`
- Mô phỏng Monte Carlo từ phân bố dự báo đã hiệu chỉnh, mô phỏng tồn FIFO theo hạn sử dụng qua nhiều ngày.
- Chi phí = (giá vốn − giá thanh lý) × lượng hết hạn + (biên lợi nhuận + phạt mất khách) × lượng thiếu.
- Ràng buộc: ngân sách, sức chứa kho lạnh, MOQ của nhà cung cấp.
- Đầu ra: 3 phương án (An toàn ≈ P85, Cân bằng ≈ tỷ lệ tới hạn, Tiết kiệm ≈ P50), mỗi phương án có số lượng theo SKU, tổng tiền, % bỏ dự kiến, % hết hàng dự kiến và lý do.

### 5.2 `suggest_markdown`
- Đầu vào: tồn hiện tại, hạn dùng, dự báo bán theo khung giờ còn lại.
- Chọn mức giảm trong {0, 10, 20, 30, 50%} cho từng khung giờ, dùng hệ số co giãn giả lập, tối đa doanh thu thu hồi trừ lượng phải bỏ.

### 5.3 `transfer_stock`
- Ghép cửa hàng dư với cửa hàng thiếu theo dự báo.
- Nếu tiền tiết kiệm > chi phí chuyến: tạo instance VRP (depot = cửa hàng dư, khách type 1 = cửa hàng thiếu) và gọi `optimize_routes`.
- Agent trình bày so sánh bằng tiền giữa giảm giá và điều chuyển.

## 6. Định tuyến (`routing/`)
- routing-PL là git submodule, không sửa, chạy trong container riêng; gọi `POST /solve/manual` (depot, customers với earliest/latest/service_time/type, lockers, num_vehicles, vehicle_capacity, solver).
- Giới hạn của solver: một depot, khoảng cách Euclid. Vì vậy:
  - Gom đơn theo đợt 30–60 phút, mỗi cửa hàng là một depot.
  - Adapter: lat/lng → tọa độ phẳng tính bằng km (UTM zone 48N), nhân hệ số đường vòng khoảng 1,3; khung giờ tính bằng phút từ đầu ca.
  - Lựa chọn nhận: tận nhà → type 1; điểm nhận → type 2; linh hoạt (giảm phí ship) → type 3.
  - Điểm nhận / tủ: sảnh chung cư hoặc tại cửa hàng.
- Giới hạn khoảng 100 đơn mỗi đợt, có time limit cho solver; cache kết quả cho demo.
- Benchmark: PACO / SA / ALNS (có sẵn trong repo) / "mỗi đơn một chuyến", trên các chỉ số km, số xe, số đơn trễ, runtime.
- Hướng nâng cấp: ma trận khoảng cách OSRM (cần sửa C++).

## 7. Agent (`agent/`)
- LLM tool-calling, cấu hình qua biến môi trường; mặc định Claude Sonnet 5.5 (`claude-sonnet-5-5`).
- Vòng làm việc: hiểu ý → hiển thị kế hoạch → gọi công cụ → trả lời theo khuôn cố định: Đề xuất / Vì sao / Độ tin cậy / Giả định / Việc cần bạn duyệt.
- Công cụ chỉ đọc/tính toán: agent tự gọi. Công cụ hành động: chỉ tạo bản nháp; thực thi khi người dùng bấm Duyệt (do API kiểm soát, không do LLM).
- `query_data`: text-to-SQL chỉ đọc trên view được whitelist, bắt buộc bộ lọc `chain_id`, giới hạn số dòng, chạy bằng role DB chỉ đọc.
- `render_chart`: trả về spec ECharts để UI render.
- Bộ kiểm tra nguồn số liệu: mọi con số trong câu trả lời phải khớp output của một tool call trong lượt đó. Không khớp → agent viết lại một lần; vẫn sai → gắn cờ "chưa kiểm chứng" trên UI.
- Dữ liệu từ bảng và nội dung người dùng nhập vào bản ghi được bọc là dữ liệu, không là lệnh (chống prompt injection).
- Audit log: lệnh, kế hoạch, tool call (input/output), quyết định duyệt/từ chối; hiển thị ở tab "Lịch sử quyết định".

## 8. Bảo mật và quyền riêng tư
- Cách ly tenant: mỗi chuỗi có workspace và schema DB riêng; phân quyền theo vai trò chủ chuỗi / quản lý cửa hàng.
- FL: chỉ trao đổi trọng số; DP và secure aggregation tùy chọn; server không thấy dữ liệu bán hàng.
- Dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP): địa chỉ chỉ dùng cho định tuyến, làm tròn tọa độ khi lưu phân tích; không gửi tên hay số điện thoại khách lên LLM; LLM chỉ nhận số liệu tổng hợp.

## 9. Giao diện (`web/`)
- Next.js + FastAPI gateway (`api/`). Streamlit của routing-PL giữ làm công cụ nội bộ so sánh solver.
- Bên trái: chat, các bước kế hoạch, thẻ đề xuất có nút Duyệt / Sửa / Bỏ.
- Bên phải: dashboard theo ngữ cảnh: biểu đồ dự báo có dải P10–P90, bảng 3 phương án, bản đồ lộ trình (Leaflet/OSM), thẻ tin cậy; hover số liệu để xem nguồn.
- Tab "Mạng lưới FL": số chuỗi tham gia, mức cải thiện so với Local-only, ε hiện tại.
- Tab "Giả định dữ liệu": nhãn SIMULATED, tham số, lộ trình sang dữ liệu thật.
- Chế độ demo dự phòng: kịch bản đã ghi, không cần LLM hoặc mạng.

## 10. Cấu trúc repo
```
freshmesh/
├─ data_sim/     # bộ sinh dữ liệu giả lập
├─ forecasting/  # mô hình quantile, conformal, Flower client/server
├─ decision/     # plan_inventory, suggest_markdown, transfer_stock
├─ routing/      # adapter + routing-PL (submodule)
├─ agent/        # vòng tool-calling, guardrail, audit log
├─ api/          # FastAPI gateway
├─ web/          # Next.js
├─ docs/         # spec, giả định dữ liệu, kết quả thí nghiệm, pitch deck
└─ docker-compose.yml
```

## 11. Kiểm thử
- Unit test (TDD): `decision/` (ví dụ newsvendor với phân bố đã biết trả về Q đúng tỷ lệ tới hạn; FIFO hết hạn đúng ngày); adapter routing (instance đúng định dạng `src/data/readme.txt` của routing-PL; chuyển đổi tọa độ); conformal (độ phủ trên dữ liệu tổng hợp).
- Thí nghiệm chạy lại được, xuất CSV và biểu đồ: Local/FL/Centralized; ε so với WAPE; mô phỏng 30 ngày so với baseline trung bình 7 ngày; benchmark solver.
- Bộ đánh giá agent: khoảng 30 câu lệnh tiếng Việt, kiểm tra chọn đúng công cụ, 0 số chưa kiểm chứng, 0 hành động tự thực thi.
- E2E: 3 luồng demo trên UI.

## 12. Lộ trình (khoảng 5 tuần, lát cắt dọc)

| Tuần | Kết quả |
|---|---|
| 1 | Bộ sinh dữ liệu, dự báo local, `plan_inventory`, adapter PACO → luồng 1 chạy bằng CLI |
| 2 | Agent, API, UI tối thiểu → luồng 1 và 3 trên web |
| 3 | FL (Flower, FedPer), conformal, thẻ tin cậy, thí nghiệm Local/FL/Centralized |
| 4 | Markdown, điều chuyển (luồng 2), DP, guardrail, tab Mạng lưới FL |
| 5 | Đánh bóng UX, bộ đánh giá agent, benchmark solver, pitch deck, video dự phòng |

Chia việc gợi ý: (1) Data/Forecast/FL · (2) Decision + Routing · (3) Agent + API · (4) Frontend/UX · (5) Pitch, nghiên cứu người dùng, thí nghiệm.

## 13. Rủi ro
| Rủi ro | Giảm thiểu |
|---|---|
| LLM chậm hoặc mất mạng lúc demo | Chế độ kịch bản đã ghi; nút bấm thay chat |
| PACO chạy lâu | ≤ 100 đơn/đợt, time limit, cache |
| Giám khảo nghi ngờ dữ liệu giả | Tab Giả định dữ liệu, lộ trình POS thật, kế hoạch pilot |
| "Sao không train tập trung?" | Persona là các chuỗi độc lập, đối thủ của nhau; thí nghiệm cold-start |
| Phạm vi phình to | Thứ tự cắt: secure aggregation → DP → luồng 2. Lõi phải giữ: luồng 1 + luồng 3 + FL cơ bản |
| Số liệu BHX cũ | Ghi năm nguồn trong deck; chỉ dùng làm bằng chứng ngành |
