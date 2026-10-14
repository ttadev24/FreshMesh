# Giả định dữ liệu FreshMesh

Dữ liệu FreshMesh gồm ba lớp, mỗi dòng ghi rõ nguồn trong cột `source` (mã nguồn dữ liệu, xem
`docs/data-provenance.md`):

- **Dữ liệu công khai thật**: vị trí cửa hàng, điểm nhận và điểm giao (OpenStreetMap, `OSM_HCMC`/`OSM_HCMC_SITES`),
  lượng mưa ngày TP.HCM (Open-Meteo, `WEATHER_OPENMETEO_ARCHIVE`/`_FORECAST`), ngày lễ và âm lịch (`CALENDAR_VN`).
- **Tham số do AI sinh** (`AI_PARAMS_CATALOG`, `AI_PARAMS_DEMAND`, `AI_PARAMS_CHAINS`, `AI_PARAMS_ORDERS`,
  `AI_PARAMS_ELASTICITY`, `AI_PARAMS_LOTS`): danh mục SKU và giá, mức nhu cầu và các hệ số thứ/lịch âm/lễ/mưa/khuyến
  mãi, hồ sơ 3 chuỗi, hành vi đơn online, hệ số co giãn giá, cơ cấu tuổi lô tồn kho. Do Claude Haiku 5.5
  (`claude-haiku-5-5`) đề xuất theo hiểu biết chung, có lý do (`basis_vi`), mức tin cậy và cờ phỏng đoán cho từng số;
  toàn văn prompt và câu trả lời được lưu để kiểm tra (`docs/data-provenance.md`). Đây là **ước lượng hợp lý, không
  phải số đo**.
- **Do chương trình sinh/cố định**: doanh số ngày, khuyến mãi, tồn kho theo lô, đơn online được chương trình
  `data_sim` (quá trình ngẫu nhiên có seed) mở rộng từ các tham số AI ở trên (`GEN_FROM_AI_PARAMS_V1`, nhãn "Sinh bằng
  chương trình từ tham số do AI (Claude Haiku 5.5) tạo; không phải giao dịch thật"). Phần vẫn là hằng số của chương
  trình mang mã `GEN_PROGRAM_V1` (liệt kê ở mục "Phần vẫn do chương trình cố định"). Không có dữ liệu công khai cấp
  cửa hàng–mặt hàng ở Việt Nam; **không có giao dịch thật nào** trong demo.

Tài liệu này liệt kê các tham số mô phỏng (giá trị hiện hành lấy từ `data_real/generated/*.json`), các giả định kinh
tế dùng cho ra quyết định và lộ trình chuyển sang dữ liệu bán hàng thật. Mã nguồn: `data_real/ai_params.py` (prompt,
schema, kiểm tra), `data_sim/` (hằng số `data_sim.ASSUMPTIONS`, bảng `assumptions` trong mỗi DB chuỗi),
`data_real/` (tải và lưu dữ liệu công khai).

## Tổng quan và cách tạo lại dữ liệu

- Lệnh: `uv run python -m data_real build` (= `uv run python -m data_sim --out data --seed 42`). Không cần mạng:
  dữ liệu công khai đọc từ các tệp đã cam kết trong `data_real/snapshot/` và `data_real/holidays_vn.json`, tham số AI
  đọc từ `data_real/generated/*.json` (đã cam kết). Chạy lại sẽ ghi đè; cùng seed, cùng snapshot và cùng tệp tham số
  cho nội dung DB giống hệt. Thiếu một tệp tham số thì lệnh dừng với thông báo tiếng Việt yêu cầu chạy
  `uv run python -m data_real generate-params` (không có số mặc định thay thế). Tải lại nguồn công khai:
  `uv run python -m data_real fetch`.
- Mỗi chuỗi một file SQLite riêng: `data/chains/<chain_id>.sqlite` (cách ly tenant bằng file DB riêng).
- Ngày cuối của lịch sử (ngày "hôm nay" của demo): **`SIM_AS_OF = 2026-09-30`** (`data_sim.SIM_AS_OF`).
- Lịch sử bán hàng: 365 ngày (2025-10-01 → 2026-09-30) cho cửa hàng đã hoạt động; 14 ngày cho cửa hàng mới.
- Bảng `calendar` kéo dài thêm 60 ngày sau `SIM_AS_OF` để mô hình dự báo có đặc trưng lịch cho tương lai.
- Bảng `weather` gồm 365 ngày lịch sử + 14 ngày sau `SIM_AS_OF`, là **lượng mưa thật** của TP.HCM từ Open-Meteo
  (lưu trữ tới 2026-10-12, 2026-10-13 và 2026-10-14 là dự báo); giống nhau ở cả 3 chuỗi.
- Bảng `calendar`: `is_holiday` theo danh sách ngày nghỉ chính thức 2025–2026 (`data_real/holidays_vn.json`,
  có trích dẫn văn bản); ngày âm, Tết, rằm, mùng 1 tính bằng `lunardate`.
- Mọi phần ngẫu nhiên lấy từ `numpy.random.default_rng([seed, ...])`: luồng riêng cho chọn vị trí cửa hàng và
  từng chuỗi.

## Chuỗi, cửa hàng và tọa độ

| Chuỗi | Tên | Tệp khách | Cửa hàng (loại khu vực) | Cửa hàng mới |
|---|---|---|---|---|
| `CHAIN_A` | Bếp Xanh Mart | Hộ gia đình khu dân cư, mua đồ tươi nấu cơm tối, cuối tuần đông | 6: dân cư, dân cư, gần chợ, dân cư, văn phòng, dân cư | CH6 |
| `CHAIN_B` | Tiện Lợi Phố | Nhân viên văn phòng, giờ trưa, đồ uống/đồ ăn liền, vắng cuối tuần | 5: văn phòng, văn phòng, dân cư, văn phòng, gần chợ | — |
| `CHAIN_C` | Chợ Nhà | Khách đi chợ truyền thống, nhạy rằm/mùng 1 và mưa, mua sáng sớm | 7: chợ, chợ, dân cư, chợ, dân cư, văn phòng, chợ | CH7 |

- Mã cửa hàng: `<A|B|C>-CH<n>`; tên hiển thị `CH<n> <phường>` với phường là nút `place=suburb` OSM gần nhất
  (tên phường sau sắp xếp 2025). Không dùng tên/thương hiệu thật của cửa hàng OSM; mã OSM gốc ở bảng `osm_refs`.
- Cửa hàng mới (cold-start): `is_new = 1`, `history_days = 14`, `opened_date = SIM_AS_OF − 13 ngày`. Cửa hàng
  khác: `history_days = 365`, ngày mở cửa trước đầu kỳ lịch sử.
- **Tọa độ thật từ OpenStreetMap**: cửa hàng đặt tại vị trí của cửa hàng tiện lợi/siêu thị mini thật
  (`shop=convenience|supermarket`) trong trích xuất OSM nội thành (vĩ độ 10,70–10,86; kinh độ 106,60–106,82).
  (Trước đây tọa độ lấy từ instance routing-PL `R101_co_100` ánh xạ lên TP.HCM; cách này đã bỏ.)
- **Chuỗi theo cụm địa lý** (tâm, bán kính): A — Bình Thạnh/Phú Nhuận/Gò Vấp (10,805; 106,700; 3,2 km);
  B — Quận 1/3/4 cũ (10,776; 106,697; 2,6 km); C — Quận 5/6/10/11 cũ, Chợ Lớn (10,756; 106,655; 3,2 km).
  Cửa hàng OSM thuộc cụm có tâm gần nhất trong bán kính.
- **Loại khu vực suy ra từ OSM**: có chợ (`amenity=marketplace`) trong 350 m → gần chợ; ≥ 8 văn phòng
  (`office=*`, `building=office|commercial`) trong 400 m → văn phòng; còn lại → dân cư.
- **Điều kiện chọn**: quanh cửa hàng phải có ≥ 60 tòa nhà ở trong 0,3–3 km, ≥ 4 tòa ở 2,6–3,3 km, ≥ 3 tòa chung
  cư ở 0,4–1,2 km và ≥ 3 tòa nhà trong 0,5 km; hai cửa hàng bất kỳ cách nhau ≥ 1,2 km. Chọn ngẫu nhiên theo seed,
  ô khan hiếm nhất trước, thử lại tối đa 200 lần.

## Danh mục hàng (SKU)

30 SKU cho mọi cửa hàng: 14 hàng tươi (hạn bán 1–3 ngày) và 16 hàng khô. Danh sách mặt hàng, `sku_id` và nhóm hàng do
chương trình cố định (các mô-đun khác và demo tham chiếu tới, ví dụ `SKU_RAU_MUONG`); **tên hiển thị kèm quy cách, giá
vốn, giá bán, giá thu hồi, hạn bán, MOQ, mã nhà cung cấp, ô kho lạnh và độ phổ biến do AI đề xuất**
(`AI_PARAMS_CATALOG`, prompt `P20261014T004848-c28383bcd2`, tệp `data_real/generated/catalog.json`). Giá VND/đơn vị,
mặt bằng bán lẻ TP.HCM 2026 theo ước lượng của mô hình, không phải giá khảo sát.

| sku_id | Tên (AI) | Giá vốn | Giá bán | Thu hồi | Hạn (ngày) | MOQ | Nhà cung cấp | Ô lạnh | Độ phổ biến | Tin cậy |
|---|---|---|---|---|---|---|---|---|---|---|
| `SKU_RAU_MUONG` | Rau muống (bó 500g) | 8.000 | 12.000 | 0 | 2 | 20 | `SUP_RAU_XANH` | 0,3 | 7 | medium |
| `SKU_CAI_NGOT` | Cải ngọt (bó 500g) | 9.500 | 14.000 | 0 | 2 | 20 | `SUP_RAU_XANH` | 0,3 | 6 | medium |
| `SKU_XA_LACH` | Xà lách (cây 300g) | 11.000 | 16.000 | 0 | 3 | 15 | `SUP_RAU_DALAT` | 0,3 | 3 | medium |
| `SKU_CA_CHUA` | Cà chua (kg) | 22.000 | 32.000 | 1.000 | 3 | 20 | `SUP_RAU_XANH` | 0,4 | 5 | medium |
| `SKU_RAU_THOM` | Rau thơm (bó 100g) | 3.800 | 6.000 | 0 | 2 | 30 | `SUP_RAU_XANH` | 0,2 | 4 | medium |
| `SKU_THIT_BA_ROI` | Thịt heo ba rọi (khay 500g) | 95.000 | 120.000 | 60.000 | 2 | 10 | `SUP_THIT` | 1 | 8 | medium |
| `SKU_THIT_NAC_VAI` | Thịt heo nạc vai (khay 500g) | 88.000 | 110.000 | 55.000 | 2 | 10 | `SUP_THIT` | 1 | 7 | medium |
| `SKU_BO_THAN` | Thịt bò thăn (khay 300g) | 140.000 | 185.000 | 100.000 | 2 | 5 | `SUP_THIT` | 0,8 | 3 | low |
| `SKU_UC_GA` | Ức gà phi lê (khay 500g) | 60.000 | 78.000 | 40.000 | 2 | 10 | `SUP_THIT` | 0,9 | 5 | medium |
| `SKU_CA_BASA` | Cá basa phi lê (khay 500g) | 66.000 | 88.000 | 40.000 | 2 | 8 | `SUP_HAISAN` | 0,9 | 4 | medium |
| `SKU_TOM_THE` | Tôm thẻ (khay 300g) | 72.000 | 95.000 | 45.000 | 2 | 6 | `SUP_HAISAN` | 0,8 | 3 | low |
| `SKU_TRUNG_GA` | Trứng gà (vỉ 10 quả) | 32.000 | 40.000 | 20.000 | 3 | 12 | `SUP_TRUNG` | 0,6 | 9 | medium |
| `SKU_SUA_CHUA` | Sữa chua (lốc 4 hũ 100g) | 20.000 | 28.000 | 10.000 | 3 | 24 | `SUP_SUA` | 0,5 | 6 | medium |
| `SKU_DAU_HU` | Đậu hũ non (bịch 300g) | 8.000 | 12.000 | 3.000 | 2 | 20 | `SUP_DAUHU` | 0,4 | 5 | medium |
| `SKU_GAO_ST25` | Gạo ST25 (túi 5kg) | 150.000 | 185.000 | 140.000 | 365 | 4 | `SUP_TAPHOA` | 0 | 6 | medium |
| `SKU_MI_GOI` | Mì gói (gói 75g) | 3.900 | 5.000 | 3.000 | 240 | 30 | `SUP_TAPHOA` | 0 | 9 | medium |
| `SKU_NUOC_MAM` | Nước mắm (chai 500ml) | 26.000 | 36.000 | 20.000 | 540 | 12 | `SUP_GIAVI` | 0 | 6 | medium |
| `SKU_DAU_AN` | Dầu ăn (chai 1 lít) | 40.000 | 52.000 | 32.000 | 365 | 12 | `SUP_GIAVI` | 0 | 7 | medium |
| `SKU_DUONG` | Đường (gói 1kg) | 19.000 | 26.000 | 15.000 | 730 | 20 | `SUP_GIAVI` | 0 | 4 | medium |
| `SKU_NUOC_TUONG` | Nước tương (chai 500ml) | 21.000 | 30.000 | 16.000 | 540 | 12 | `SUP_GIAVI` | 0 | 4 | medium |
| `SKU_HAT_NEM` | Hạt nêm (gói 400g) | 30.000 | 42.000 | 24.000 | 540 | 12 | `SUP_GIAVI` | 0 | 4 | medium |
| `SKU_SUA_TUOI` | Sữa tươi tiệt trùng (hộp 180ml) | 7.000 | 9.000 | 5.000 | 180 | 48 | `SUP_SUATUOI` | 0 | 6 | medium |
| `SKU_NUOC_SUOI` | Nước suối (chai 500ml) | 4.000 | 6.000 | 2.500 | 365 | 24 | `SUP_NUOCUONG` | 0 | 8 | medium |
| `SKU_TRA_XANH` | Trà xanh (chai 455ml) | 7.500 | 11.000 | 5.000 | 270 | 24 | `SUP_NUOCUONG` | 0 | 5 | medium |
| `SKU_CA_PHE` | Cà phê hòa tan (hộp 10 gói) | 32.000 | 45.000 | 24.000 | 365 | 12 | `SUP_NUOCUONG` | 0 | 4 | medium |
| `SKU_BANH_QUY` | Bánh quy (hộp 200g) | 26.000 | 38.000 | 18.000 | 240 | 12 | `SUP_BANHKEO` | 0 | 5 | medium |
| `SKU_SNACK` | Snack khoai tây (gói 60g) | 10.000 | 15.000 | 6.000 | 180 | 24 | `SUP_BANHKEO` | 0 | 7 | medium |
| `SKU_NUOC_RUA_CHEN` | Nước rửa chén (chai 750g) | 30.000 | 42.000 | 22.000 | 730 | 12 | `SUP_GIADUNG` | 0 | 5 | medium |
| `SKU_GIAY_VS` | Giấy vệ sinh (lốc 10 cuộn) | 44.000 | 58.000 | 35.000 | 1095 | 6 | `SUP_GIADUNG` | 0 | 6 | medium |
| `SKU_BOT_GIAT` | Bột giặt (túi 3kg) | 72.000 | 98.000 | 55.000 | 730 | 6 | `SUP_GIADUNG` | 0 | 5 | medium |

- Kiểm tra bắt buộc (bị từ chối nếu sai): đủ 30 `sku_id`, tên bắt đầu bằng tên sản phẩm cho sẵn,
  `unit_price > unit_cost > salvage_price ≥ 0`, giá bán bội số 500 đ, biên gộp 12–60%, hàng tươi hạn 1–3 ngày và có ô
  kho lạnh 0,1–2, hàng khô hạn 60–1.095 ngày và không chiếm kho lạnh, MOQ 1–200, mã nhà cung cấp dạng `SUP_…`.
- Mô hình tự đánh dấu là phỏng đoán nhiều nhất: giá thu hồi và độ phổ biến (mọi SKU), MOQ (phần lớn); giá thịt bò và
  tôm có độ tin cậy thấp.
- Giá bán theo chuỗi = giá trên × hệ số giá của chuỗi (AI: A 1,00; B 1,08; C 0,97), làm tròn 500 đ; chương trình dừng
  nếu giá sau hệ số không cao hơn giá vốn.
- `demand_weight` được chuẩn hóa trong mỗi nhóm hàng thành tỷ trọng của SKU trong lượng bán của nhóm.

## Mô hình doanh số ngày

`units ~ NegBin(mean = μ, shape = k)` với

`μ = nền nhóm × tỷ trọng SKU × hệ số thứ × hệ số lịch âm/lễ × hệ số mưa × khuyến mãi × xu hướng`

Cơ chế (công thức, thứ tự rút ngẫu nhiên, seed) là của chương trình; **mọi hệ số dưới đây do AI đề xuất**
(`AI_PARAMS_DEMAND`, prompt `P20261014T004920-fdb3b60047`; `AI_PARAMS_CHAINS`, prompt `P20261014T004938-1a0c646ad5`).
Mô hình tự đánh giá phần lớn các hệ số lịch âm, mưa, khuyến mãi là độ tin cậy thấp / phỏng đoán.

- **Nền nhóm hàng** (đơn vị/ngày của cả nhóm tại một cửa hàng; chuỗi tham chiếu, ngày thường, không mưa):

| Nhóm | Dân cư | Gần chợ | Văn phòng | Tin cậy |
|---|---|---|---|---|
| `vegetable` | 120 | 180 | 40 | medium |
| `meat` | 70 | 90 | 20 | medium |
| `seafood` | 40 | 60 | 10 | low |
| `egg` | 50 | 60 | 25 | medium |
| `dairy` | 30 | 35 | 15 | low |
| `tofu` | 25 | 35 | 8 | low |
| `staple` | 40 | 35 | 30 | low |
| `condiment` | 30 | 30 | 20 | low |
| `beverage` | 35 | 30 | 90 | medium |
| `snack` | 25 | 25 | 60 | medium |
| `household` | 15 | 12 | 15 | low |

  Nền SKU = nền nhóm theo loại khu vực × tỷ trọng SKU trong nhóm × độ ưa hàng tươi của chuỗi (với hàng tươi) × quy mô
  chuỗi × hệ số riêng cửa hàng U(0,7; 1,4) × lognormal(0; 0,2) theo cửa hàng–SKU.
- **Thứ trong tuần** (T2…CN): dân cư 0,9 · 0,9 · 0,92 · 0,95 · 1,0 · 1,2 · 1,25; gần chợ 0,95 · 0,95 · 0,97 · 1,0 ·
  1,02 · 1,1 · 1,15; văn phòng 1,05 · 1,08 · 1,08 · 1,05 · 1,0 · 0,4 · 0,3.
- **Lịch âm** (thư viện `lunardate`; s = độ nhạy lịch âm của chuỗi: A 1,0; B 0,5; C 1,5):
  - 10 ngày trước Tết (số ngày do chương trình cố định): tăng dần tới × (1 + 0,8·s) với thịt/hải sản, × (1 + 0,5·s)
    với nhóm khác.
  - Mùng 1–3 Tết: × max(0,15; 1 − 0,7·s); mùng 4–7: × 0,7.
  - Rằm và mùng 1 hằng tháng: rau/đậu hũ × (1 + 0,4·s) (ăn chay); thịt/hải sản × (1 − 0,15·s) (chặn dưới 0,3).
- **Ngày nghỉ lễ chính thức** (`is_holiday`, không tính các ngày Tết đã xử lý ở trên): văn phòng × 0,5; khu khác
  × 1,1. Năm 2025–2026: 1/1; 5 ngày Tết theo thông báo (27–31/1/2025, 16–20/2/2026); Giỗ Tổ (7/4/2025;
  26/4/2026 và nghỉ bù 27/4/2026); 30/4; 1/5; 1/9 và 2/9; 24/11/2026 (Ngày Văn hóa Việt Nam).
- **Mưa**: ≥ 2 mm là mưa nhẹ, ≥ 20 mm là mưa lớn (ngưỡng của chương trình). Hệ số AI (nhẹ / lớn): dân cư 0,8 / 0,55;
  gần chợ 0,75 / 0,5; văn phòng 0,85 / 0,6; mức giảm nhân với độ nhạy mưa của chuỗi (A 1,0; B 0,8; C 1,4), chặn dưới
  0,3. Lượng mưa là số liệu thật của Open-Meteo (cột `rain_mm`); chỉ phản ứng của doanh số với mưa là giả định.
- **Khuyến mãi**: đợt 4 ngày, xác suất bắt đầu mỗi ngày mỗi SKU theo chuỗi (A 2,0%; B 3,0%; C 1,5%; hàng tươi
  × 0,6 — hệ số 0,6 của chương trình); giá × 0,85, lượng bán × 1,6. Cột `price` là giá thực bán ngày đó, `promo = 1`
  khi có khuyến mãi.
- **Xu hướng**: tăng trưởng/năm A 8%, B 3%, C 5% (bằng 1,0 tại `SIM_AS_OF`).
- **Quy mô và độ ưa hàng tươi của chuỗi**: quy mô A 1,0; B 0,8; C 1,1; độ ưa hàng tươi A 1,2; B 0,6; C 1,5.
- **Nhiễu**: Negative Binomial, tham số hình dạng k: A 8,0; B 5,0; C 6,0.
- **Non-IID giữa chuỗi**: khác nhau về cơ cấu loại khu vực, độ ưa hàng tươi, độ nhạy lịch âm và mưa, tần suất
  khuyến mãi, mức nhiễu và xu hướng — phục vụ thí nghiệm học liên kết.
- Ràng buộc kiểm tra trước khi chấp nhận câu trả lời AI: tỷ số cuối tuần/ngày thường văn phòng 0,2–0,65, dân cư
  1,12–1,6; mưa lớn giảm mạnh hơn mưa nhẹ; độ ưa hàng tươi C > A > B; độ nhạy lịch âm của C ≥ 1,2; mọi hệ số trong
  khoảng ghi trong prompt (`data_real/ai_params.py`).

## Tồn kho hiện tại (inventory_lots)

Tồn kho cuối ngày `SIM_AS_OF`, theo lô (`received_date`, `expires_on = received_date + shelf_life_days`), không có
lô nào đã hết hạn. m = trung bình bán/ngày 7 ngày gần nhất của cửa hàng–SKU. Các khoảng tỷ lệ do AI đề xuất
(`AI_PARAMS_LOTS`, prompt `P20261014T005019-710eedb645`); chương trình rút đều trong khoảng.

- Hàng tươi hạn L ngày: một lô cho mỗi ngày nhập trong L ngày gần nhất; lô mới nhất 0,4–1,2·m, lô giữa
  0,2–0,8·m, lô cũ nhất (hết hạn ngày mai) 0,05–0,5·m.
- Hàng khô: 1–3 lô nhập 3–45 ngày trước, mỗi lô 3–20·m.
- **Kịch bản dư hàng** (kịch bản demo của chương trình, `GEN_PROGRAM_V1`): ở mọi chuỗi, cửa hàng CH3 có lô rau (`vegetable`) 2,6–3,4·m hết hạn ngày mai
  ("Còn nhiều rau ở CH3"). **Kịch bản thiếu hàng**: cửa hàng đã hoạt động gần CH3 nhất chỉ còn 0,05–0,2·m rau.
  Với seed 42: `CHAIN_A` dư ở `A-CH3`, thiếu ở `A-CH1` (cách 1,38 km).
- View `v_stock` có cột `days_to_expiry` tính so với `SIM_AS_OF` (không phụ thuộc đồng hồ máy).
- **Quy ước hạn dùng**: `expires_on` là **ngày bán được cuối cùng (tính cả ngày đó)**; lô bị hủy vào cuối ngày
  `expires_on`. Hàng nhập về cuối ngày `received_date`, nên số ngày bán được = `shelf_life_days` (từ
  `received_date + 1` đến `expires_on`). Lô có `days_to_expiry = 1` phải bán hết hoặc giảm giá trong ngày 2026-10-01.
- **Đồng hồ demo**: lịch sử đến hết 2026-09-30; tồn kho là tồn cuối ngày 2026-09-30 = tồn đầu ngày 2026-10-01;
  ngày dự báo thứ nhất là 2026-10-01; đợt giao online hiện tại bắt đầu 2026-10-01 09:00.

## Đơn online, điểm nhận và đợt giao

- **Đợt gom đơn**: thực tế 30–60 phút/đợt; dữ liệu giả lập dùng đợt **45 phút**. Đợt hiện tại bắt đầu lúc
  `SIM_BATCH_START = 2026-10-01T09:00`; đơn thuộc đợt có `created_at ∈ [08:15, 09:00)`
  (`data_sim.batch_created_range()`). Mốc phút 0 của `earliest/latest` là `SIM_BATCH_START`.
- Tham số hành vi đơn do AI đề xuất (`AI_PARAMS_ORDERS`, prompt `P20261014T004958-84bbeedddc`); chương trình cố định
  cơ chế, đợt 45 phút, việc chặn số đơn mỗi đợt trong 12–40 và số đơn "gấp" 1–2 mỗi đợt (để demo luôn có đơn có
  nguy cơ trễ).
- Mỗi cửa hàng 12–40 đơn trong đợt hiện tại: AI đề xuất dân cư 12–22, gần chợ 15–28, văn phòng 14–26, nhân quy mô
  chuỗi rồi chặn trong 12–40; cửa hàng mới × 0,6 (vẫn ≥ 12). Luôn ≤ `max_orders_per_batch` của routing.
- Đơn lịch sử: 14 ngày gần nhất, số đơn/ngày theo khu vực (AI: dân cư 40–120, chợ 30–90, văn phòng 25–70; cửa hàng
  mới × 0,6), phân bố theo giờ 6h–21h theo tỷ trọng theo giờ của AI (mục "Giả định kinh tế"). Khung giờ của đơn lịch
  sử tính từ đầu đợt của chính nó. Tỷ lệ đơn "gấp" trong lịch sử: 2%.
- Vị trí: tâm một **tòa nhà ở thật trong OSM** (chọn ngẫu nhiên): giao tận nhà trong 0,3–3 km quanh cửa hàng; đơn
  nhận tại điểm nhận ở tòa nhà trong 0,5 km (quầy) hoặc 0,8 km (sảnh) quanh điểm đó; đơn linh hoạt luôn ở tòa
  nhà trong 0,8 km quanh một sảnh (khách chọn "linh hoạt" vì gần điểm nhận). Mã OSM của tòa nhà ở `osm_refs`.
- `delivery_mode` (AI): tận nhà 55%, điểm nhận 30%, linh hoạt 15% (tương ứng customer type 1/2/3 của routing-PL);
  40% đơn nhận tại điểm nhận chọn quầy cửa hàng, còn lại chọn sảnh chung cư.
  `demand` (số "đơn vị tải" trên xe máy) 1 / 2 / 3 với xác suất 0,6 / 0,3 / 0,1; `service` 3–8 phút (điểm nhận 2 phút).
- Khung giờ: `earliest` ∈ {0, 15, …, 60}, `latest = earliest + 60–120` phút, nâng lên ít nhất thời gian đi + 10
  phút và không quá 240 phút (`shift_minutes`). Có chủ ý 1–2 đơn "gấp" mỗi đợt (2% × số đơn, chặn trong 1–2) ở xa
  2,6–3,3 km với `latest` nhỏ hơn thời gian đi → được báo **có nguy cơ trễ** (`unreachable_in_window`).
- **Điểm nhận** (`pickup_points`): mỗi cửa hàng có quầy nhận tại cửa hàng (id `<store_id>-counter`, trùng
  `routing.models.counter_id`) và 2–3 tòa chung cư thật (`building=apartments` trong OSM) cách 0,4–1,2 km, ưu
  tiên tòa có tên đọc được (tên hiển thị "Sảnh <tên OSM>"); khung giờ 0–240 phút.
  **Lưu ý tích hợp**: adapter routing tự thêm quầy cửa hàng, nên khi dựng `Batch` hãy bỏ dòng có
  `pickup_point_id = counter_id(store_id)` khỏi `pickup_points` (đơn vẫn được tham chiếu tới id đó hợp lệ).
- View `v_online_orders` làm tròn tọa độ 3 chữ số thập phân (~100 m) và không có trường thông tin khách hàng
  (Nghị định 13/2023/NĐ-CP).

## Giả định định tuyến

- Tốc độ xe máy trung bình nội thành: **20 km/h** (`RoutingConfig.speed_kmh`).
- Hệ số đường vòng: **1,3** (quãng đường thực ≈ 1,3 × đường chim bay; `RoutingConfig.detour_factor`).
  Như vậy 1 km đường chim bay ≈ 3,9 phút di chuyển. Đo bằng OSRM (hồ sơ ô tô) trên 200 cặp cửa hàng–tòa nhà
  thật cho trung vị 1,58 (IQR 1,40–1,99), tức 1,3 thấp hơn số đo ô tô; xe máy có thể thấp hơn ô tô. Chi tiết:
  `docs/data-real-detour.md`.
- Ca giao 240 phút; bán kính điểm nhận cho đơn linh hoạt 1 km; tối đa 50 đơn/đợt (theo `routing.config`).

## Giả định kinh tế cho ra quyết định

- **Hệ số co giãn giá khi giảm giá cận hạn** (do AI đề xuất, `AI_PARAMS_ELASTICITY`, prompt
  `P20261014T005011-2dcf2d241e`; chưa ước lượng từ dữ liệu thật): lượng bán sau giảm = lượng bán gốc × (1 − mức
  giảm)^e. Bảng dùng giá trị điểm làm tròn 1 chữ số; khoảng hợp lý AI nêu trong ngoặc ở cột "khoảng".

| Nhóm | e | khoảng | | Nhóm | e | khoảng |
|---|---|---|---|---|---|---|
| vegetable | −2,2 | −3,0…−1,5 | | staple | −0,8 | −1,2…−0,4 |
| meat | −2,6 | −3,5…−1,8 | | condiment | −0,6 | −1,0…−0,3 |
| seafood | −2,8 | −3,8…−1,9 | | beverage | −1,0 | −1,5…−0,5 |
| egg | −1,9 | −2,6…−1,3 | | snack | −1,1 | −1,6…−0,6 |
| dairy | −2,4 | −3,2…−1,6 | | household | −0,7 | −1,1…−0,3 |
| tofu | −2,0 | −2,8…−1,4 | | | | |

  Ví dụ rau giảm 30%: lượng bán × 0,7^−2,2 ≈ × 2,19. AI tự đánh giá độ tin cậy thấp cho hàng tươi, đồ uống, snack;
  trung bình cho hàng khô thiết yếu.
- Mức giảm cho phép: 0%, 10%, 20%, 30%, 50%.
- Tỷ trọng doanh số theo giờ (6h–21h) theo loại khu vực (do AI đề xuất, `AI_PARAMS_ORDERS`; chương trình chuẩn hóa
  tổng = 1), dùng để chia dự báo ngày thành khung giờ cho markdown và phân bố giờ đặt đơn online
  (`ASSUMPTIONS["hourly_sales_share"]`): dân cư đỉnh 18–20h, gần chợ đỉnh 6–7h và 18–19h, văn phòng đỉnh 12–13h.
- Phạt mất khách khi hết hàng: 0,5 × biên lợi nhuận đơn vị (cộng thêm vào biên lợi nhuận bị mất).
- Chi phí điều chuyển bằng xe máy: 5.000 đ/km đường + 20.000 đ/chuyến.

## Phần vẫn do chương trình cố định (`GEN_PROGRAM_V1`)

Những phần sau không hỏi AI và không có nguồn công khai, vì là cơ chế/kịch bản của phần mềm hoặc cần ổn định cho các
mô-đun khác:

- Cơ chế mô phỏng: phân phối Negative Binomial, công thức μ, thứ tự rút số ngẫu nhiên và seed; lô FIFO; đợt đơn 45
  phút; 10 ngày "trước Tết"; ngưỡng mưa 2 mm / 20 mm; chặn dưới 0,3 cho hệ số mưa và hệ số thịt/cá ngày rằm; hàng
  tươi khuyến mãi × 0,6 tần suất; cận dưới khung giờ = thời gian đi + 10 phút; ngày mở cửa của cửa hàng đã hoạt
  động lùi ngẫu nhiên 30–1.500 ngày trước đầu kỳ lịch sử.
- Danh mục 11 nhóm hàng, 30 mặt hàng và `sku_id` (API, dự báo, demo và kiểm thử tham chiếu tới).
- Chuỗi: tên hư cấu, mô tả tệp khách, số cửa hàng, loại khu vực từng cửa hàng, cửa hàng mới (cold-start).
- Kịch bản demo: dư rau hết hạn ngày mai ở CH3 (2,6–3,4·m), thiếu rau ở cửa hàng gần nhất (0,05–0,2·m); mỗi đợt
  12–40 đơn và 1–2 đơn "gấp".
- Tài khoản demo; các giả định kinh tế/định tuyến: mức giảm giá cho phép, phạt hết hàng 0,5, chi phí điều chuyển,
  tốc độ, hệ số đường vòng, ca giao, bán kính điểm nhận.
- Bảng `chains` và `users` mang mã `GEN_PROGRAM_V1`; bảng `assumptions` ghi mã nguồn theo từng khóa
  (`markdown_elasticity` → `AI_PARAMS_ELASTICITY`, `hourly_sales_share` → `AI_PARAMS_ORDERS`, `promo` →
  `AI_PARAMS_DEMAND`, còn lại `GEN_PROGRAM_V1`).

## Nhãn nguồn dữ liệu và giới hạn

- Cột `source` chứa mã nguồn dữ liệu, không có giá trị chung `SIMULATED`: `AI_PARAMS_CATALOG` cho `skus`,
  `GEN_FROM_AI_PARAMS_V1` cho `daily_sales`, `inventory_lots`, `online_orders`, `GEN_PROGRAM_V1` cho `chains`,
  `OSM_HCMC_SITES` cho cửa hàng/điểm nhận đặt trên vị trí OSM thật; bảng `data_sources` ghi nguồn của thời tiết, lịch
  và tọa độ. API/giao diện hiển thị nhãn theo `provenance.label_vi(mã)`; `provenance.describe(mã)` trả kèm toàn văn
  prompt.
- Tham số do AI đề xuất là **ước lượng hợp lý** cho mini-mart TP.HCM theo hiểu biết chung của mô hình, **không phải
  số đo, khảo sát hay giao dịch thật**; mô hình không truy cập Internet và bị cấm trích nguồn. Phần lớn số có
  `confidence` = low/medium và nhiều số có `is_guess = true`. Chưa được hiệu chỉnh bằng dữ liệu bán hàng thật; kết quả
  demo minh họa cách hệ thống hoạt động, không phải con số kinh doanh thực tế.
- Vị trí đơn là tòa nhà thật nhưng đơn hàng là mô phỏng; không có khách hàng hay dữ liệu cá nhân thật.

## Lộ trình chuyển sang dữ liệu thật

1. **Kết nối POS**: xuất dữ liệu từ KiotViet / Sapo (báo cáo bán hàng theo ngày–mặt hàng, tồn kho theo lô,
   nhập hàng, danh mục hàng hóa và giá vốn) qua file Excel/CSV hoặc API của nhà cung cấp POS.
2. **Ánh xạ vào cùng schema**: `stores`, `skus`, `daily_sales`, `inventory_lots`, `online_orders` giữ nguyên cấu
   trúc; cột `source` đổi thành mã nguồn mới đăng ký trong registry (ví dụ `POS_KIOTVIET` / `POS_SAPO`); thời tiết,
   vị trí OSM, lịch âm và ngày lễ giữ nguyên nguồn hiện tại. Khi đó các tham số AI không còn dùng để sinh dữ liệu:
   giá/giá vốn/hạn bán lấy từ danh mục POS, mức nhu cầu và hệ số thứ/lịch âm/mưa/khuyến mãi được mô hình dự báo học
   trực tiếp từ doanh số thật, cơ cấu lô lấy từ tồn kho theo lô, hành vi đơn từ lịch sử đơn online.
3. **Pilot 2–3 mini-mart** trong 4–8 tuần: so sánh dự báo với thực tế, so tham số AI với số đo (giá, biên, tỷ lệ
   hàng cận hạn, tỷ trọng theo giờ), ước lượng lại hệ số co giãn giá từ các đợt giảm giá thật, đo tốc độ giao thực tế để hiệu chỉnh `speed_kmh` và `detour_factor`.
4. Mở rộng lên nhiều chuỗi để học liên kết (mỗi chuỗi giữ dữ liệu tại chỗ, chỉ chia sẻ trọng số mô hình).
