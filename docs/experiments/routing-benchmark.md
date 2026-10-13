<!-- BEGIN GENERATED -->
# Benchmark định tuyến / routing benchmark (spec §1.4 #4, §6)

Nguồn dữ liệu: **Mô phỏng bằng chương trình (tham số giả định); © OpenStreetMap contributors (ODbL); Vị trí thật từ OpenStreetMap (ODbL), gán chuỗi bằng chương trình**. Đợt đơn demo hiện tại (cửa sổ 45 phút trước 2026-10-01 09:00) của 18 cửa hàng ở 3 chuỗi, 404 đơn, 30 đơn bị loại trước khi định tuyến (không kịp giao ngay cả khi đi thẳng — giống nhau cho mọi phương pháp). Đội xe 4 × 30 đơn vị; km = phút di chuyển × 20 km/h (đã gồm hệ số đường vòng 1,3).

| Phương pháp / method | Tổng km | Tổng xe / vehicles | Điểm dừng trễ / late stops | Đợt vượt đội xe | Runtime TB (s) | Tiết kiệm km vs baseline | Tốt hơn baseline cả km và số xe ở mọi đợt |
|---|---|---|---|---|---|---|---|
| Mỗi đơn một chuyến | 1306.8 | 374 | 0 | 18 | 0.0 | — | — |
| PACO | 367.7 | 39 | 9 | 0 | 2.5 | 71.9% | có / yes |
| ALNS | 363.6 | 40 | 11 | 0 | 7.4 | 72.2% | có / yes |

Baseline "vehicles" = số chuyến (mỗi đơn một chuyến khứ hồi từ cửa hàng). Runtime = thời gian solver tự báo (lần giải đầu tiên; kết quả được cache theo hash của đợt).

## Theo cửa hàng / per store (km · xe · trễ)

| Cửa hàng | Đơn | Định tuyến | Mỗi đơn một chuyến | PACO | ALNS |
|---|---|---|---|---|---|
| A-CH1 | 27 | 25 | 68.6 · 25 · 0 | 21.8 · 3 · 1 | 21.6 · 3 · 2 |
| A-CH2 | 28 | 26 | 61.4 · 26 · 0 | 18.9 · 3 · 1 | 19.0 · 3 · 1 |
| A-CH3 | 21 | 19 | 81.3 · 19 · 0 | 25.4 · 2 · 0 | 25.6 · 2 · 0 |
| A-CH4 | 26 | 24 | 74.9 · 24 · 0 | 18.5 · 3 · 1 | 19.0 · 3 · 0 |
| A-CH5 | 17 | 16 | 79.3 · 16 · 0 | 23.3 · 3 · 0 | 23.6 · 3 · 0 |
| A-CH6 | 13 | 12 | 46.9 · 12 · 0 | 14.5 · 1 · 1 | 14.6 · 1 · 1 |
| B-CH1 | 17 | 16 | 60.6 · 16 · 0 | 23.1 · 2 · 0 | 21.6 · 2 · 1 |
| B-CH2 | 15 | 14 | 48.7 · 14 · 0 | 17.4 · 1 · 0 | 17.4 · 1 · 0 |
| B-CH3 | 20 | 18 | 72.9 · 18 · 0 | 20.2 · 2 · 0 | 20.2 · 3 · 0 |
| B-CH4 | 18 | 16 | 53.5 · 16 · 0 | 14.6 · 1 · 0 | 14.8 · 2 · 0 |
| B-CH5 | 16 | 15 | 48.1 · 15 · 0 | 14.4 · 2 · 0 | 14.3 · 2 · 0 |
| C-CH1 | 26 | 24 | 96.7 · 24 · 0 | 24.8 · 2 · 0 | 24.6 · 2 · 1 |
| C-CH2 | 24 | 22 | 66.5 · 22 · 0 | 18.8 · 2 · 0 | 19.1 · 2 · 0 |
| C-CH3 | 37 | 35 | 107.4 · 35 · 0 | 24.7 · 3 · 1 | 24.6 · 3 · 2 |
| C-CH4 | 33 | 31 | 113.2 · 31 · 0 | 28.0 · 3 · 2 | 28.0 · 3 · 2 |
| C-CH5 | 27 | 25 | 89.8 · 25 · 0 | 22.3 · 2 · 1 | 21.1 · 2 · 0 |
| C-CH6 | 25 | 23 | 84.7 · 23 · 0 | 22.7 · 3 · 0 | 20.3 · 2 · 0 |
| C-CH7 | 14 | 13 | 52.1 · 13 · 0 | 14.3 · 1 · 1 | 14.3 · 1 · 1 |

![km per store](routing_benchmark_km.svg)
<!-- END GENERATED -->

## Phân tích (viết tay) / analysis (hand-written)

**Tiêu chí §1.4 #4 — ĐẠT / holds.** Lần chạy này dùng dữ liệu đã dựng lại trên vị trí thật từ OpenStreetMap (cửa hàng,
điểm nhận, tòa nhà làm điểm giao; `docs/data-provenance.md`); đơn hàng vẫn do chương trình sinh. Trên cùng 18 đợt
đơn (404 đơn, 30 đơn bị loại trước khi định tuyến, **374 đơn được định tuyến**), PACO đi tổng **367,7 km so với
1.306,8 km** của cách "mỗi đơn một chuyến" (**−71,9%**) và dùng **39 xe so với 374 chuyến**; PACO tốt hơn baseline
cả về km lẫn số xe ở **từng** đợt (18/18). ALNS cũng vậy (363,6 km, −72,2%, 40 xe, 18/18).

- **Giả định hệ số đường vòng:** mọi số km/giờ đến ở đây tính bằng tốc độ trung bình 20 km/h × hệ số đường vòng
  1,3 trên khoảng cách đường chim bay, chưa dùng bản đồ đường phố. Phép đo OSRM (hồ sơ ô tô) **không ủng hộ** 1,3:
  trung vị 1,58 (IQR 1,40–1,99, `docs/data-real-detour.md`); hệ số của xe máy chưa được đo. Vì vậy km tuyệt đối
  (của cả PACO, ALNS và baseline) có thể bị ước lượng thấp và giờ đến có thể sớm hơn thực tế; tỷ lệ tiết kiệm so
  với baseline ít nhạy hơn vì cả hai phía cùng nhân một hệ số, nhưng số điểm trễ có thể tăng với hệ số lớn hơn.
- **Điểm dừng trễ:** PACO có 9 điểm dừng dự kiến trễ (ở 8/18 đợt), ALNS 11 (ở 8/18 đợt); baseline 0 — nhưng
  baseline 0 là do cách định nghĩa (mỗi đơn một xe đi thẳng từ phút 0, cần tới 12–35 chuyến/đợt trong khi đội chỉ
  có 4 xe, nên cả 18 đợt đều vượt đội xe và trên thực tế không chạy song song được). Cần nói rõ khi demo: PACO
  giảm km mạnh nhưng không bảo đảm 0 trễ.
- **ALNS** (chạy qua `docker exec … /app/backend/bin/test --solver alns`, tham số `alns.param.yaml` của
  routing-PL vì API không hỗ trợ ALNS): km thấp hơn PACO một chút (363,6 so với 367,7), nhưng nhiều hơn 1 xe (40),
  nhiều điểm trễ hơn (11 so với 9) và chậm hơn (7,4 s so với 2,5 s trung bình mỗi đợt).
- **SA — không có số / no SA numbers:** ở lần chạy trước, binary SA của routing-PL dừng với `std::out_of_range`
  (`unordered_map::at`, tra `customer2node` trong `Solver.cpp`) trên instance FreshMesh: thử qua API với A-CH1
  (medium, lỗi sau 85 s) và B-CH4 (small, 8,6 s), và qua CLI với tham số `src/parameters/sa.param.yaml` (B-CH4):
  đều lỗi. Vì vậy benchmark mặc định chỉ chạy PACO và ALNS (`DEFAULT_METHODS` trong `simulation/routing_bench.py`);
  lần chạy này **không thử lại SA** trên instance mới, nên chưa biết SA còn lỗi hay không. Không sửa vì submodule
  routing-PL không được chỉnh; không có số SA nào được báo cáo.
- **Runtime:** cả PACO lẫn ALNS đều được giải mới ở 18/18 đợt (cột `cached` = 0 trong CSV); runtime là thời gian
  solver tự báo. PACO trung bình 2,5 s/đợt (0,45–13,2 s, tổng ~45 s), ALNS 7,4 s/đợt (1,5–36,7 s, tổng ~2,2 phút).
  Giải tuần tự, không song song để không tranh solver với API.

**English.** On the 18 demo batches of the rebuilt data (real OSM sites; program-generated orders; 374 routed
orders) PACO drives 367.7 km vs 1,306.8 km for one-trip-per-order (−71.9%) with 39 vehicles vs 374 trips, better
on both in every batch (18/18), so criterion §1.4 #4 holds. ALNS: 363.6 km (−72.2%), 40 vehicles, also 18/18.
Caveats: PACO has 9 late stops (in 8/18 batches), ALNS 11; the baseline's 0 is by construction (one direct trip per
order, which a 4-rider fleet cannot dispatch at once — all 18 batches exceed the fleet). Mean solver runtime
2.5 s per batch for PACO vs 7.4 s for ALNS (all solved fresh, none cached). All km and arrival times assume a
detour factor of 1.3, which the OSRM car-profile measurement does not support (median 1.58, IQR 1.40–1.99,
`docs/data-real-detour.md`; motorbikes not measured), so absolute km are likely understated. SA was not re-run:
on the earlier instances the routing-PL SA binary aborted with `std::out_of_range` (API and CLI, small and
medium), SA is therefore excluded from the default benchmark, the submodule is not modified, and no SA numbers
are reported.
