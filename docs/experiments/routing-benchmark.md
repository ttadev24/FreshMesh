<!-- BEGIN GENERATED -->
# Benchmark định tuyến / routing benchmark (spec §1.4 #4, §6)

Nguồn dữ liệu: **Sinh bằng chương trình từ tham số do AI (Claude Haiku 5.5) tạo; không phải giao dịch thật; © OpenStreetMap contributors (ODbL); Vị trí thật từ OpenStreetMap (ODbL), gán chuỗi bằng chương trình**. Đợt đơn demo hiện tại (cửa sổ 45 phút trước 2026-10-01 09:00) của 18 cửa hàng ở 3 chuỗi, 302 đơn, 18 đơn bị loại trước khi định tuyến (không kịp giao ngay cả khi đi thẳng — giống nhau cho mọi phương pháp). Đội xe 4 × 30 đơn vị; km = phút di chuyển × 20 km/h (đã gồm hệ số đường vòng 1,3).

| Phương pháp / method | Tổng km | Tổng xe / vehicles | Điểm dừng trễ / late stops | Đợt vượt đội xe | Runtime TB (s) | Tiết kiệm km vs baseline | Tốt hơn baseline cả km và số xe ở mọi đợt |
|---|---|---|---|---|---|---|---|
| Mỗi đơn một chuyến | 985.7 | 284 | 0 | 18 | 0.0 | — | — |
| PACO | 320.8 | 32 | 29 | 0 | 0.6 | 67.5% | có / yes |
| ALNS | 322.3 | 24 | 27 | 0 | 2.0 | 67.3% | có / yes |

Baseline "vehicles" = số chuyến (mỗi đơn một chuyến khứ hồi từ cửa hàng). Runtime = thời gian solver tự báo (lần giải đầu tiên; kết quả được cache theo hash của đợt).

## Theo cửa hàng / per store (km · xe · trễ)

| Cửa hàng | Đơn | Định tuyến | Mỗi đơn một chuyến | PACO | ALNS |
|---|---|---|---|---|---|
| A-CH1 | 15 | 14 | 29.9 · 14 · 0 | 15.5 · 2 · 1 | 15.5 · 1 · 0 |
| A-CH2 | 19 | 18 | 52.9 · 18 · 0 | 22.0 · 2 · 2 | 22.0 · 1 · 2 |
| A-CH3 | 19 | 18 | 88.8 · 18 · 0 | 23.7 · 2 · 0 | 23.7 · 2 · 0 |
| A-CH4 | 22 | 21 | 72.9 · 21 · 0 | 19.9 · 2 · 6 | 21.1 · 2 · 4 |
| A-CH5 | 26 | 25 | 106.5 · 25 · 0 | 26.1 · 2 · 6 | 26.1 · 2 · 6 |
| A-CH6 | 13 | 12 | 36.7 · 12 · 0 | 18.3 · 1 · 1 | 18.3 · 1 · 1 |
| B-CH1 | 12 | 11 | 42.7 · 11 · 0 | 17.7 · 1 · 1 | 17.7 · 1 · 1 |
| B-CH2 | 12 | 11 | 49.8 · 11 · 0 | 17.9 · 1 · 0 | 17.9 · 1 · 0 |
| B-CH3 | 12 | 11 | 36.0 · 11 · 0 | 17.2 · 2 · 0 | 17.3 · 2 · 0 |
| B-CH4 | 14 | 13 | 27.8 · 13 · 0 | 13.3 · 2 · 0 | 13.3 · 1 · 0 |
| B-CH5 | 17 | 16 | 35.0 · 16 · 0 | 7.4 · 2 · 1 | 8.0 · 1 · 1 |
| C-CH1 | 23 | 22 | 59.9 · 22 · 0 | 18.5 · 2 · 1 | 18.5 · 2 · 1 |
| C-CH2 | 16 | 15 | 72.1 · 15 · 0 | 17.4 · 2 · 3 | 17.4 · 1 · 3 |
| C-CH3 | 16 | 15 | 55.6 · 15 · 0 | 16.4 · 2 · 0 | 16.4 · 1 · 0 |
| C-CH4 | 24 | 23 | 74.2 · 23 · 0 | 19.4 · 2 · 5 | 19.4 · 2 · 6 |
| C-CH5 | 14 | 13 | 47.5 · 13 · 0 | 17.4 · 1 · 0 | 16.9 · 1 · 0 |
| C-CH6 | 16 | 15 | 60.0 · 15 · 0 | 19.4 · 2 · 2 | 19.4 · 1 · 2 |
| C-CH7 | 12 | 11 | 37.5 · 11 · 0 | 13.7 · 2 · 0 | 13.7 · 1 · 0 |

![km per store](routing_benchmark_km.svg)
<!-- END GENERATED -->

## Phân tích (viết tay) / analysis (hand-written)

**Tiêu chí §1.4 #4 — ĐẠT / holds.** Lần chạy này dùng dữ liệu dựng lại trên vị trí thật từ OpenStreetMap (cửa hàng,
điểm nhận, tòa nhà làm điểm giao) với đơn online do chương trình mở rộng từ tham số do AI (Claude Haiku 5.5) sinh
(`GEN_FROM_AI_PARAMS_V1`; `docs/data-provenance.md`) — không phải đơn thật. Trên 18 đợt đơn (302 đơn, 18 đơn bị loại
trước khi định tuyến, **284 đơn được định tuyến**), PACO đi tổng **320,8 km so với 985,7 km** của cách "mỗi đơn một
chuyến" (**−67,5%**, từng đợt −48,2% đến −78,8%) và dùng **32 xe so với 284 chuyến**; PACO tốt hơn baseline cả về km
lẫn số xe ở **từng** đợt (18/18). ALNS cũng vậy (322,3 km, −67,3%, 24 xe, 18/18). Đợt của CHAIN_B nhỏ hơn trong dữ
liệu này (12–17 đơn/đợt, so với 13–26 ở A và 12–24 ở C).

- **Giả định hệ số đường vòng:** mọi số km/giờ đến ở đây tính bằng tốc độ trung bình 20 km/h × hệ số đường vòng
  1,3 trên khoảng cách đường chim bay, chưa dùng bản đồ đường phố. Phép đo OSRM (hồ sơ ô tô) **không ủng hộ** 1,3:
  trung vị 1,58 (IQR 1,40–1,99, `docs/data-real-detour.md`); hệ số của xe máy chưa được đo. Vì vậy km tuyệt đối
  (của cả PACO, ALNS và baseline) có thể bị ước lượng thấp và giờ đến có thể sớm hơn thực tế; tỷ lệ tiết kiệm so
  với baseline ít nhạy hơn vì cả hai phía cùng nhân một hệ số, nhưng số điểm trễ có thể tăng với hệ số lớn hơn.
- **Điểm dừng trễ:** PACO có 29 điểm dừng dự kiến trễ (khoảng 10% trong 284 điểm, ở 11/18 đợt), ALNS 27 (ở 10/18
  đợt); baseline 0 — nhưng baseline 0 là do cách định nghĩa (mỗi đơn một xe đi thẳng từ phút 0, cần tới 11–25
  chuyến/đợt trong khi đội chỉ có 4 xe, nên cả 18 đợt đều vượt đội xe và trên thực tế không chạy song song được).
  Cần nói rõ khi demo: PACO giảm km mạnh nhưng không bảo đảm 0 trễ.
- **ALNS** (chạy qua `docker exec … /app/backend/bin/test --solver alns`, tham số `alns.param.yaml` của
  routing-PL vì API không hỗ trợ ALNS): tổng km cao hơn PACO một chút (322,3 so với 320,8; PACO ngắn hơn ở 4 đợt,
  dài hơn ở 2, bằng nhau ở 12), nhưng dùng ít xe hơn (24 so với 32; ít hơn ở 8/18 đợt), ít điểm trễ hơn một chút
  (27 so với 29) và chậm hơn (2,0 s so với 0,6 s trung bình mỗi đợt).
- **SA — không có số / no SA numbers:** ở lần chạy đầu, binary SA của routing-PL dừng với `std::out_of_range`
  (`unordered_map::at`, tra `customer2node` trong `Solver.cpp`) trên instance FreshMesh: thử qua API với A-CH1
  (medium, lỗi sau 85 s) và B-CH4 (small, 8,6 s), và qua CLI với tham số `src/parameters/sa.param.yaml` (B-CH4):
  đều lỗi. Vì vậy benchmark mặc định chỉ chạy PACO và ALNS (`DEFAULT_METHODS` trong `simulation/routing_bench.py`);
  lần chạy này **không chạy SA** trên instance mới, nên chưa biết SA còn lỗi hay không. Không sửa vì submodule
  routing-PL không được chỉnh; không có số SA nào được báo cáo.
- **Runtime:** cả PACO lẫn ALNS đều được giải mới ở 18/18 đợt (cột `cached` = 0 trong CSV); runtime là thời gian
  solver tự báo. PACO trung bình 0,62 s/đợt (0,33–1,26 s, tổng ~11 s), ALNS 1,98 s/đợt (1,43–2,64 s, tổng ~36 s).
  Giải tuần tự, không song song để không tranh solver với API.

**English.** On the 18 demo batches of the current data (real OSM sites; online orders program-expanded from
AI-generated parameters, not real orders; 284 routed orders) PACO drives 320.8 km vs 985.7 km for
one-trip-per-order (−67.5%; −48.2% to −78.8% per batch) with 32 vehicles vs 284 trips, better on both in every
batch (18/18), so criterion §1.4 #4 holds. ALNS: 322.3 km (−67.3%), 24 vehicles, also 18/18. CHAIN_B batches are
smaller in this data (12–17 orders, vs 13–26 in A and 12–24 in C). PACO vs ALNS: PACO is slightly shorter in total
(shorter in 4 batches, longer in 2, equal in 12) but uses more vehicles (32 vs 24) and has slightly more late stops.
Caveats: PACO has 29 late stops (about 10% of routed stops, in 11/18 batches), ALNS 27 (in 10/18); the baseline's 0
is by construction (one direct trip per order, 11–25 trips per batch, which a 4-rider fleet cannot dispatch at
once — all 18 batches exceed the fleet). Mean solver runtime 0.62 s per batch for PACO (0.33–1.26 s) vs 1.98 s for
ALNS (1.43–2.64 s); all solved fresh, none cached. All km and arrival times assume a detour factor of 1.3, which the
OSRM car-profile measurement does not support (median 1.58, IQR 1.40–1.99, `docs/data-real-detour.md`; motorbikes
not measured), so absolute km are likely understated. SA was not run: on the earlier instances the routing-PL SA
binary crashed with `std::out_of_range` (API and CLI, small and medium), SA is therefore excluded from the default
benchmark, the submodule is not modified, and no SA numbers are reported.
