# Giả định dữ liệu FreshMesh

Toàn bộ dữ liệu trong hệ thống hiện tại là **dữ liệu giả lập** (`source = 'SIMULATED'`). Mọi bảng có cột
`source` đều mang giá trị `SIMULATED`; mọi kết quả hiển thị cho người dùng đều gắn nhãn này. Tài liệu này
liệt kê các tham số giả lập, các giả định kinh tế dùng cho ra quyết định và lộ trình chuyển sang dữ liệu thật.
Mã nguồn tương ứng: `data_sim/` (hằng số Python `data_sim.ASSUMPTIONS`, bảng `assumptions` trong mỗi DB chuỗi).

## Tổng quan và cách tạo lại dữ liệu

- Lệnh: `uv run python -m data_sim --out data --seed 42`. Chạy lại sẽ ghi đè; cùng seed cho nội dung DB giống hệt.
- Mỗi chuỗi một file SQLite riêng: `data/chains/<chain_id>.sqlite` (cách ly tenant bằng file DB riêng).
- Ngày cuối của lịch sử (ngày "hôm nay" của demo): **`SIM_AS_OF = 2026-09-30`** (`data_sim.SIM_AS_OF`).
- Lịch sử bán hàng: 365 ngày (2025-10-01 → 2026-09-30) cho cửa hàng đã hoạt động; 14 ngày cho cửa hàng mới.
- Bảng `calendar` kéo dài thêm 60 ngày sau `SIM_AS_OF` để mô hình dự báo có đặc trưng lịch cho tương lai.
- Bảng `weather` gồm 365 ngày lịch sử + 14 ngày sau `SIM_AS_OF` (coi là "dự báo thời tiết" giả lập); giống
  nhau ở cả 3 chuỗi vì cùng một thành phố.
- Mọi phần ngẫu nhiên lấy từ `numpy.random.default_rng([seed, ...])`: luồng riêng cho thời tiết, vị trí cửa
  hàng và từng chuỗi.

## Chuỗi, cửa hàng và tọa độ

| Chuỗi | Tên | Tệp khách | Cửa hàng (loại khu vực) | Cửa hàng mới |
|---|---|---|---|---|
| `CHAIN_A` | Bếp Xanh Mart | Hộ gia đình khu dân cư, mua đồ tươi nấu cơm tối, cuối tuần đông | 6: dân cư, dân cư, gần chợ, dân cư, văn phòng, dân cư | CH6 |
| `CHAIN_B` | Tiện Lợi Phố | Nhân viên văn phòng, giờ trưa, đồ uống/đồ ăn liền, vắng cuối tuần | 5: văn phòng, văn phòng, dân cư, văn phòng, gần chợ | — |
| `CHAIN_C` | Chợ Nhà | Khách đi chợ truyền thống, nhạy rằm/mùng 1 và mưa, mua sáng sớm | 7: chợ, chợ, dân cư, chợ, dân cư, văn phòng, chợ | CH7 |

- Mã cửa hàng: `<A|B|C>-CH<n>`; tên hiển thị `CH<n> <khu vực>` (khu vực là quận/phường gần nhất theo tâm
  xấp xỉ, chỉ để dễ đọc).
- Cửa hàng mới (cold-start): `is_new = 1`, `history_days = 14`, `opened_date = SIM_AS_OF − 13 ngày`. Cửa hàng
  khác: `history_days = 365`, ngày mở cửa trước đầu kỳ lịch sử.
- **Ánh xạ tọa độ**: lấy 100 điểm khách hàng của instance routing-PL `routing/routing-PL/src/data/100/R101_co_100.txt`
  (mặt phẳng x ∈ [2, 67], y ∈ [3, 77]). Ánh xạ tuyến tính x → kinh độ [106,62; 106,78], y → vĩ độ [10,72; 10,84]
  (khoảng 17 km × 13 km nội thành TP.HCM). Cửa hàng được chọn từ các điểm này theo thứ tự hoán vị theo seed,
  giữ khoảng cách tối thiểu 1,2 km giữa hai cửa hàng bất kỳ.

## Danh mục hàng (SKU)

30 SKU cho mọi cửa hàng: 14 hàng tươi (hạn 1–3 ngày) và 16 hàng khô. Giá tính bằng VND/đơn vị.

| Nhóm (`category`) | SKU tươi | Hạn dùng |
|---|---|---|
| `vegetable` | Rau muống, Cải ngọt, Xà lách Đà Lạt, Cà chua, Rau thơm | 1–3 ngày |
| `meat` | Thịt heo ba rọi, Thịt heo nạc vai, Thịt bò thăn, Ức gà phi lê | 2 ngày |
| `seafood` | Cá basa phi lê, Tôm thẻ tươi | 1 ngày |
| `egg`, `dairy`, `tofu` | Trứng gà ta, Sữa chua, Đậu hũ non | 2–3 ngày |

Hàng khô: `staple` (gạo ST25, mì gói), `condiment` (nước mắm, dầu ăn, đường, nước tương, hạt nêm),
`beverage` (sữa tươi tiệt trùng, nước suối, trà xanh, cà phê hòa tan), `snack` (bánh quy, snack khoai tây),
`household` (nước rửa chén, giấy vệ sinh, bột giặt); hạn 180–730 ngày.

- `unit_cost` (giá vốn), `unit_price` (giá bán niêm yết), `salvage_price` (giá thu hồi khi hết hạn/cận hạn:
  bán cho đối tác, làm suất ăn nhân viên…) theo mức giá bán lẻ TP.HCM 2025–2026, luôn
  `unit_price > unit_cost > salvage_price ≥ 0`.
- Giá bán theo chuỗi: A × 1,00; B × 1,06 (tiện lợi); C × 0,95 (giá chợ); làm tròn 500 đ.
- `moq` theo quy cách thùng/lốc của nhà cung cấp; `supplier_id` theo nhà cung cấp giả lập (rau Đà Lạt, thịt,
  hải sản, sữa, tạp hóa tổng…).
- `cold_storage_units`: số "ô kho lạnh" mỗi đơn vị chiếm (thịt/cá 1,0; rau 0,5; trứng 0,3; hàng khô 0).

## Mô hình doanh số ngày

`units ~ NegBin(mean = μ, shape = k)` với

`μ = nền × hệ số thứ × hệ số lịch âm/lễ × hệ số mưa × khuyến mãi × xu hướng`

- **Nền**: `base_daily_units` của SKU (cửa hàng dân cư tham chiếu) × hệ số khu vực (dân cư 1,0; gần chợ 1,25;
  văn phòng 0,8) × cơ cấu nhóm hàng theo khu vực (văn phòng: đồ uống × 1,8, snack × 1,6, thịt × 0,6, hải sản × 0,5;
  gần chợ: rau × 1,25, thịt × 1,2, hải sản × 1,3) × độ ưa hàng tươi của chuỗi (A 1,15; B 0,75; C 1,35) × quy mô
  chuỗi (A 1,0; B 0,85; C 1,2) × hệ số riêng cửa hàng U(0,8; 1,25) × lognormal(0; 0,15) theo SKU.
- **Thứ trong tuần** (T2…CN): dân cư 0,95 · 0,93 · 0,95 · 0,97 · 1,03 · 1,15 · 1,20; gần chợ 1,00 · 0,97 · 0,98 ·
  1,00 · 1,05 · 1,12 · 1,10; văn phòng 1,12 · 1,10 · 1,10 · 1,12 · 1,08 · 0,60 · 0,45.
- **Lịch âm** (thư viện `lunardate`; s = độ nhạy lịch âm của chuỗi: A 1,0; B 0,6; C 1,5):
  - 10 ngày trước Tết: tăng dần tới × (1 + 0,9·s) với thịt/hải sản, × (1 + 0,55·s) với nhóm khác.
  - Mùng 1–3 Tết: × max(0,15; 1 − 0,65·s) (khách về quê, cửa hàng mở ngắn giờ); mùng 4–7: × 0,8.
  - Rằm và mùng 1 hằng tháng: rau/đậu hũ × (1 + 0,35·s) (ăn chay); thịt/hải sản × max(0,5; 1 − 0,18·s).
- **Ngày lễ dương lịch** (1/1, 30/4, 1/5, 1/9, 2/9) và Giỗ Tổ (10/3 âm): văn phòng × 0,45; khu khác × 1,1.
  Cờ `is_holiday` cũng bật cho mùng 1–5 Tết.
- **Mưa**: ≥ 2 mm là mưa nhẹ, ≥ 20 mm là mưa lớn. Hệ số (nhẹ / lớn): dân cư 0,97 / 0,85; gần chợ 0,93 / 0,72;
  văn phòng 0,96 / 0,80; mức giảm nhân với độ nhạy mưa của chuỗi (A 1,0; B 0,8; C 1,3).
  Lượng mưa: mùa mưa (5–11) xác suất mưa 62%, lượng ~ Gamma(0,9; 16) mm; mùa khô xác suất 10%, Gamma(0,6; 5) mm.
- **Khuyến mãi**: đợt 3 ngày, xác suất bắt đầu mỗi ngày mỗi SKU theo chuỗi (A 2,0%; B 3,5%; C 1,2%; hàng tươi
  × 0,6); giá × 0,85, lượng bán × 1,45. Cột `price` là giá thực bán ngày đó, `promo = 1` khi có khuyến mãi.
- **Xu hướng**: tăng trưởng/năm A 6%, B 10%, C 3% (bằng 1,0 tại `SIM_AS_OF`).
- **Nhiễu**: Negative Binomial, tham số hình dạng k: A 8,0; B 5,0; C 3,5 (C nhiễu nhất).
- **Non-IID giữa chuỗi**: khác nhau về cơ cấu loại khu vực, độ ưa hàng tươi, độ nhạy lịch âm và mưa, tần suất
  khuyến mãi, mức nhiễu và xu hướng — phục vụ thí nghiệm học liên kết.

## Tồn kho hiện tại (inventory_lots)

Tồn kho cuối ngày `SIM_AS_OF`, theo lô (`received_date`, `expires_on = received_date + shelf_life_days`), không có
lô nào đã hết hạn. m = trung bình bán/ngày 7 ngày gần nhất của cửa hàng–SKU.

- Hàng tươi hạn L ngày: một lô cho mỗi ngày nhập trong L ngày gần nhất; lô mới nhất 0,7–1,1·m, lô giữa
  0,4–0,8·m, lô cũ nhất (hết hạn ngày mai) 0,15–0,45·m.
- Hàng khô: 1–2 lô nhập 3–45 ngày trước, mỗi lô 4–12·m.
- **Kịch bản dư hàng**: ở mọi chuỗi, cửa hàng CH3 có lô rau (`vegetable`) 2,6–3,4·m hết hạn ngày mai
  ("Còn nhiều rau ở CH3"). **Kịch bản thiếu hàng**: cửa hàng đã hoạt động gần CH3 nhất chỉ còn 0,05–0,2·m rau.
  Với seed 42: `CHAIN_A` dư ở `A-CH3`, thiếu ở `A-CH2`.
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
- Mỗi cửa hàng 12–40 đơn trong đợt hiện tại (dân cư 22–36, gần chợ 16–28, văn phòng 12–22, nhân quy mô chuỗi;
  cửa hàng mới 12–16), luôn ≤ `max_orders_per_batch` của routing.
- Đơn lịch sử: 14 ngày gần nhất, số đơn/ngày theo khu vực (dân cư 70–110, chợ 50–85, văn phòng 40–70), phân bố
  theo giờ 6h–21h giống tỷ trọng doanh số theo giờ. Khung giờ của đơn lịch sử tính từ đầu đợt của chính nó.
- Vị trí: trong bán kính 0,3–3 km quanh cửa hàng; đơn nhận tại điểm nhận nằm trong 0,5 km quanh điểm đó; 60%
  đơn linh hoạt nằm trong 0,8 km quanh một sảnh chung cư (để solver có thể chọn điểm nhận).
- `delivery_mode`: tận nhà 55%, điểm nhận 20%, linh hoạt 25% (tương ứng customer type 1/2/3 của routing-PL).
  `demand` 1–3; `service` 3–6 phút (điểm nhận 2 phút).
- Khung giờ: `earliest` ∈ {0, 15, …, 150}, `latest = earliest + 45–90` phút, nâng lên ít nhất thời gian đi + 10
  phút và không quá 240 phút (`shift_minutes`). Có chủ ý 1–2 đơn "gấp" mỗi đợt ở xa 2,6–3,3 km với `latest`
  nhỏ hơn thời gian đi → được báo **có nguy cơ trễ** (`unreachable_in_window`).
- **Điểm nhận** (`pickup_points`): mỗi cửa hàng có quầy nhận tại cửa hàng (id `<store_id>-counter`, trùng
  `routing.models.counter_id`) và 2–3 sảnh chung cư cách 0,4–1,2 km; khung giờ 0–240 phút.
  **Lưu ý tích hợp**: adapter routing tự thêm quầy cửa hàng, nên khi dựng `Batch` hãy bỏ dòng có
  `pickup_point_id = counter_id(store_id)` khỏi `pickup_points` (đơn vẫn được tham chiếu tới id đó hợp lệ).
- View `v_online_orders` làm tròn tọa độ 3 chữ số thập phân (~100 m) và không có trường thông tin khách hàng
  (Nghị định 13/2023/NĐ-CP).

## Giả định định tuyến

- Tốc độ xe máy trung bình nội thành: **20 km/h** (`RoutingConfig.speed_kmh`).
- Hệ số đường vòng: **1,3** (quãng đường thực ≈ 1,3 × đường chim bay; `RoutingConfig.detour_factor`).
  Như vậy 1 km đường chim bay ≈ 3,9 phút di chuyển.
- Ca giao 240 phút; bán kính điểm nhận cho đơn linh hoạt 1 km; tối đa 50 đơn/đợt (theo `routing.config`).

## Giả định kinh tế cho ra quyết định

- **Hệ số co giãn giá khi giảm giá cận hạn** (giả định, chưa ước lượng từ dữ liệu thật):
  lượng bán sau giảm = lượng bán gốc × (1 − mức giảm)^e.

| Nhóm | e | | Nhóm | e |
|---|---|---|---|---|
| vegetable | −2,2 | | staple | −0,8 |
| tofu | −2,0 | | condiment | −0,6 |
| seafood | −1,9 | | beverage | −1,1 |
| meat | −1,6 | | snack | −1,3 |
| dairy | −1,5 | | household | −0,7 |
| egg | −1,2 | | | |

  Ví dụ rau giảm 30%: lượng bán × 0,7^−2,2 ≈ × 2,19.
- Mức giảm cho phép: 0%, 10%, 20%, 30%, 50%.
- Tỷ trọng doanh số theo giờ (6h–21h) theo loại khu vực, dùng để chia dự báo ngày thành khung giờ cho markdown
  (`ASSUMPTIONS["hourly_sales_share"]`): dân cư đỉnh 17–19h, gần chợ đỉnh 6–8h, văn phòng đỉnh 11–12h.
- Phạt mất khách khi hết hàng: 0,5 × biên lợi nhuận đơn vị (cộng thêm vào biên lợi nhuận bị mất).
- Chi phí điều chuyển bằng xe máy: 5.000 đ/km đường + 20.000 đ/chuyến.

## Nhãn SIMULATED và giới hạn

- Mọi dòng trong các bảng có cột `source` đều là `SIMULATED`; API và giao diện luôn hiển thị nhãn này.
- Tham số trên là giả định hợp lý cho mini-mart TP.HCM, chưa được hiệu chỉnh bằng dữ liệu bán hàng thật; kết
  quả demo minh họa cách hệ thống hoạt động, không phải con số kinh doanh thực tế.
- Thời tiết, khách hàng, vị trí đơn đều là giả lập; không có dữ liệu cá nhân thật.

## Lộ trình chuyển sang dữ liệu thật

1. **Kết nối POS**: xuất dữ liệu từ KiotViet / Sapo (báo cáo bán hàng theo ngày–mặt hàng, tồn kho theo lô,
   nhập hàng, danh mục hàng hóa và giá vốn) qua file Excel/CSV hoặc API của nhà cung cấp POS.
2. **Ánh xạ vào cùng schema**: `stores`, `skus`, `daily_sales`, `inventory_lots`, `online_orders` giữ nguyên cấu
   trúc; cột `source` đổi thành `POS_KIOTVIET` / `POS_SAPO`; thời tiết lấy từ nguồn quan trắc công khai; lịch âm
   và ngày lễ giữ nguyên cách tính.
3. **Pilot 2–3 mini-mart** trong 4–8 tuần: so sánh dự báo với thực tế, ước lượng lại hệ số co giãn giá từ các đợt
   giảm giá thật, đo tốc độ giao thực tế để hiệu chỉnh `speed_kmh` và `detour_factor`.
4. Mở rộng lên nhiều chuỗi để học liên kết (mỗi chuỗi giữ dữ liệu tại chỗ, chỉ chia sẻ trọng số mô hình).
