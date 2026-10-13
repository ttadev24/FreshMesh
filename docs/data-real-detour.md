# Hiệu chỉnh hệ số đường vòng (detour factor) bằng OSRM — TP.HCM

Dataset: `OSRM_DETOUR_HCMC` (loại `derived`). Kết quả đầy đủ (từng cặp điểm): `data_real/snapshot/osrm_detour.json`;
phản hồi thô của máy chủ: `data/raw/osrm/routes.jsonl` (có SHA-256 trong `data/provenance/manifest.json`).
Lệnh tạo lại: `uv run python -m data_real fetch --only osrm` (mất khoảng 4 phút vì giới hạn 1 yêu cầu/giây).

## Phương pháp

- Điểm đầu: cửa hàng tiện lợi/siêu thị mini thật trong trích xuất OSM (`OSM_HCMC`, 1.185 cửa hàng). Điểm cuối:
  tòa nhà ở thật trong OSM (`building=apartments|residential|house|terrace`, 5.908 tòa).
- 200 cặp ngẫu nhiên (seed 2026), chia đều theo khoảng cách đường chim bay như đơn giao thật:
  0,3–1 km (67 cặp), 1–2 km (67 cặp), 2–3,3 km (66 cặp).
- Quãng đường đường bộ: máy chủ demo OSRM `router.project-osrm.org`, hồ sơ `driving` (ô tô), dữ liệu OSM.
  Tuân thủ chính sách dùng thử: ≤ 1 yêu cầu/giây, User-Agent định danh FreshMesh, mục đích phi thương mại.
- Hệ số = quãng đường OSRM / khoảng cách haversine. Loại cặp có điểm bị "bắt" vào đường xa hơn 100 m
  (không cặp nào bị loại). Thời gian đo: 2026-10-13 07:42–07:46 UTC; 200/200 cặp thành công.

## Kết quả

| Nhóm khoảng cách | n | Trung vị | IQR (Q1–Q3) | P10–P90 | Trung bình |
|---|---|---|---|---|---|
| Tất cả | 200 | **1,58** | 1,40–1,99 | 1,26–3,03 | 1,97 |
| 0,3–1 km | 67 | 1,67 | 1,43–2,35 | 1,23–3,80 | 2,29 |
| 1–2 km | 67 | 1,63 | 1,47–2,13 | 1,31–3,08 | 1,99 |
| 2–3,3 km | 66 | 1,47 | 1,36–1,70 | 1,25–2,06 | 1,63 |

Chỉ 13,5% số cặp có hệ số ≤ 1,3.

## Kết luận về `RoutingConfig.detour_factor = 1,3`

- **Với hồ sơ ô tô, giá trị 1,3 không được dữ liệu ủng hộ**: trung vị đo được 1,58 (IQR 1,40–1,99), cao hơn
  1,3 ở mọi nhóm khoảng cách; đơn càng gần thì hệ số càng lớn (đường một chiều, phải vòng qua khối nhà).
- **Sai lệch đã biết của phép đo**:
  - OSRM demo chỉ có hồ sơ ô tô. Xe máy giao hàng ở TP.HCM đi được hẻm nhỏ và một số đường cấm ô tô, nên hệ số
    của xe máy nhiều khả năng **thấp hơn trung vị ô tô**; xe máy vẫn phải theo đường một chiều. Hệ số của xe máy
    **chưa được đo** — phép đo này không xác nhận cũng không bác bỏ 1,3 cho xe máy.
  - Khoảng cách haversine tính giữa hai điểm gốc (chưa "bắt" vào đường), còn quãng đường OSRM tính từ điểm đã
    bắt; tổng khoảng cách bắt có trung vị khoảng 25 m mỗi cặp (tối đa 87 m). Sai lệch này có thể theo cả hai chiều
    (đoạn từ cửa nhà ra đường không được tính vào quãng đường OSRM), cỡ vài phần trăm, rõ nhất ở nhóm 0,3–1 km.
- Hệ quả: với 1,3 thời gian di chuyển trong định tuyến có thể bị ước lượng thấp (khoảng 15–20% so với
  trung vị ô tô). Đề xuất cho nhóm routing (không sửa trong phạm vi dữ liệu): cân nhắc 1,5 hoặc chạy độ nhạy
  1,3 / 1,5 / 1,6; khi pilot, đo bằng GPS của tài xế xe máy để hiệu chỉnh.
- Mã `routing/` không bị thay đổi; giá trị trong bảng `assumptions` vẫn là 1,3 (lấy từ `RoutingConfig`).
