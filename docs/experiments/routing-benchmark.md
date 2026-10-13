<!-- BEGIN GENERATED -->
# Benchmark định tuyến / routing benchmark (spec §1.4 #4, §6)

Dữ liệu: **SIMULATED**. Đợt đơn demo hiện tại (cửa sổ 45 phút trước 2026-10-01 09:00) của 18 cửa hàng ở 3 chuỗi, 412 đơn, 30 đơn bị loại trước khi định tuyến (không kịp giao ngay cả khi đi thẳng — giống nhau cho mọi phương pháp). Đội xe 4 × 30 đơn vị; km = phút di chuyển × 20 km/h (đã gồm hệ số đường vòng 1,3).

| Phương pháp / method | Tổng km | Tổng xe / vehicles | Điểm dừng trễ / late stops | Đợt vượt đội xe | Runtime TB (s) | Tiết kiệm km vs baseline | Tốt hơn baseline cả km và số xe ở mọi đợt |
|---|---|---|---|---|---|---|---|
| Mỗi đơn một chuyến | 1411.0 | 382 | 0 | 18 | 0.0 | — | — |
| PACO | 493.3 | 45 | 12 | 0 | 6.5 | 65.0% | có / yes |
| ALNS | 494.0 | 40 | 17 | 0 | 13.8 | 65.0% | có / yes |

Baseline "vehicles" = số chuyến (mỗi đơn một chuyến khứ hồi từ cửa hàng). Runtime = thời gian solver tự báo (lần giải đầu tiên; kết quả được cache theo hash của đợt).

## Theo cửa hàng / per store (km · xe · trễ)

| Cửa hàng | Đơn | Định tuyến | Mỗi đơn một chuyến | PACO | ALNS |
|---|---|---|---|---|---|
| A-CH1 | 32 | 30 | 71.6 · 30 · 0 | 19.3 · 2 · 0 | 18.8 · 3 · 0 |
| A-CH2 | 23 | 21 | 79.0 · 21 · 0 | 31.7 · 4 · 0 | 31.2 · 2 · 0 |
| A-CH3 | 23 | 21 | 105.8 · 21 · 0 | 30.6 · 2 · 1 | 32.9 · 2 · 3 |
| A-CH4 | 29 | 27 | 86.8 · 27 · 0 | 26.2 · 3 · 3 | 26.2 · 2 · 3 |
| A-CH5 | 17 | 16 | 67.9 · 16 · 0 | 28.9 · 3 · 0 | 28.4 · 2 · 2 |
| A-CH6 | 14 | 13 | 45.8 · 13 · 0 | 17.9 · 2 · 0 | 17.9 · 2 · 0 |
| B-CH1 | 17 | 16 | 67.5 · 16 · 0 | 27.2 · 2 · 0 | 27.2 · 3 · 0 |
| B-CH2 | 14 | 13 | 47.9 · 13 · 0 | 20.6 · 2 · 0 | 20.5 · 1 · 0 |
| B-CH3 | 21 | 19 | 71.1 · 19 · 0 | 26.7 · 3 · 0 | 26.0 · 2 · 1 |
| B-CH4 | 12 | 11 | 40.9 · 11 · 0 | 21.7 · 2 · 1 | 21.4 · 2 · 1 |
| B-CH5 | 22 | 20 | 74.4 · 20 · 0 | 26.2 · 2 · 0 | 26.2 · 2 · 0 |
| C-CH1 | 27 | 25 | 98.9 · 25 · 0 | 33.4 · 3 · 2 | 33.7 · 3 · 2 |
| C-CH2 | 28 | 26 | 107.7 · 26 · 0 | 35.3 · 2 · 0 | 35.5 · 3 · 1 |
| C-CH3 | 38 | 36 | 126.5 · 36 · 0 | 33.9 · 4 · 1 | 35.1 · 3 · 2 |
| C-CH4 | 26 | 24 | 98.0 · 24 · 0 | 35.3 · 3 · 1 | 34.2 · 3 · 1 |
| C-CH5 | 34 | 32 | 103.2 · 32 · 0 | 29.3 · 2 · 0 | 29.6 · 2 · 0 |
| C-CH6 | 22 | 20 | 79.0 · 20 · 0 | 32.1 · 2 · 2 | 31.9 · 2 · 0 |
| C-CH7 | 13 | 12 | 39.2 · 12 · 0 | 17.4 · 2 · 1 | 17.4 · 1 · 1 |

![km per store](routing_benchmark_km.svg)
<!-- END GENERATED -->

## Phân tích (viết tay) / analysis (hand-written)

**Tiêu chí §1.4 #4 — ĐẠT / holds.** Trên cùng 18 đợt đơn (382 đơn được định tuyến), PACO đi tổng
**493,3 km so với 1.411,0 km** của cách "mỗi đơn một chuyến" (**−65,0%**) và dùng **45 xe so với 382 chuyến**;
PACO tốt hơn baseline cả về km lẫn số xe ở **từng** đợt (18/18).

- **Điểm dừng trễ:** PACO có 12 điểm dừng dự kiến trễ (ở 8/18 đợt), ALNS 17; baseline 0 — nhưng baseline 0 là
  do cách định nghĩa (mỗi đơn một xe đi thẳng từ phút 0, cần tới 11–36 chuyến/đợt trong khi đội chỉ có 4 xe,
  nên trên thực tế không chạy song song được). Giờ đến tính bằng tốc độ trung bình 20 km/h × hệ số đường vòng
  1,3, chưa dùng bản đồ đường phố. Cần nói rõ khi demo: PACO giảm km mạnh nhưng không bảo đảm 0 trễ.
- **ALNS** (chạy qua `docker exec … /app/backend/bin/test --solver alns`, tham số `alns.param.yaml` của
  routing-PL vì API không hỗ trợ ALNS): km gần như bằng PACO (494,0), ít xe hơn (40) nhưng nhiều điểm trễ hơn
  (17) và chậm hơn (13,8 s so với 6,5 s trung bình).
- **SA — đã thử nhưng không chạy được / attempted, not run:** API routing-PL cho chọn `solver = "sa"`, nhưng
  binary SA dừng với `std::out_of_range` (`unordered_map::at`, tra `customer2node` trong `Solver.cpp`) trên
  instance FreshMesh: thử qua API với A-CH1 (medium, lỗi sau 85 s) và B-CH4 (small, 8,6 s), và qua CLI với tham
  số `src/parameters/sa.param.yaml` (B-CH4): đều lỗi. Không sửa vì submodule routing-PL không được chỉnh;
  không có số SA nào được báo cáo.
- **Runtime:** kết quả PACO lấy từ cache của API (`data/cache/routing`, cùng hash đợt), runtime là thời gian
  solver tự báo ở lần giải đầu; ALNS được giải mới ở 17/18 đợt, riêng A-CH1 dùng lại kết quả đã có (cột `cached` trong CSV) (tổng ~3,5 phút tuần tự). Giải tuần tự, không song song để
  không tranh solver với API.

**English.** On the same 18 demo batches PACO drives 493.3 km vs 1,411.0 km for one-trip-per-order (−65.0%)
with 45 vehicles vs 382 trips, better on both in every batch, so criterion §1.4 #4 holds. Caveat: PACO has 12
late stops (ALNS 17); the baseline's 0 is by construction (one direct trip per order, which a 4-rider fleet
cannot dispatch at once). ALNS (container CLI) matches PACO on km with fewer vehicles but more late stops.
SA could not be benchmarked: the routing-PL SA binary aborts with `std::out_of_range` on these instances
(API and CLI, small and medium); the submodule is not modified, so no SA numbers are reported.
