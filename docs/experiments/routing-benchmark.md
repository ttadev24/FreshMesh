<!-- BEGIN GENERATED -->
# Benchmark định tuyến / routing benchmark (spec §1.4 #4, §6)

Nguồn dữ liệu: **Sinh bằng chương trình từ tham số do AI (Claude Haiku 5.5) tạo; không phải giao dịch thật; © OpenStreetMap contributors (ODbL); Vị trí thật từ OpenStreetMap (ODbL), gán chuỗi bằng chương trình**. Đợt đơn demo hiện tại (cửa sổ 45 phút trước 2026-10-01 09:00) của 18 cửa hàng ở 3 chuỗi, 302 đơn, 18 đơn bị loại trước khi định tuyến (không kịp giao ngay cả khi đi thẳng — giống nhau cho mọi phương pháp). Đội xe 4 × 30 đơn vị; km = phút di chuyển × 20 km/h (đã gồm hệ số đường vòng 1,3).

| Phương pháp / method | Tổng km | Tổng xe / vehicles | Điểm dừng trễ / late stops | Đợt vượt đội xe | Runtime TB (s) | Tiết kiệm km vs baseline | Tốt hơn baseline cả km và số xe ở mọi đợt |
|---|---|---|---|---|---|---|---|
| Mỗi đơn một chuyến | 985.7 | 284 | 0 | 18 | 0.0 | — | — |
| Điều phối chia vùng | 446.1 | 48 | 0 | 0 | 0.0 | 54.7% | có / yes |
| PACO | 322.6 | 33 | 26 | 0 | 5.1 | 67.3% | có / yes |
| ALNS | 322.3 | 24 | 27 | 0 | 2.0 | 67.3% | có / yes |

Baseline "vehicles" = số chuyến (mỗi đơn một chuyến khứ hồi từ cửa hàng). Runtime = thời gian solver tự báo (lần giải đầu tiên; kết quả được cache theo hash của đợt).

## Theo cửa hàng / per store (km · xe · trễ)

| Cửa hàng | Đơn | Định tuyến | Mỗi đơn một chuyến | Điều phối chia vùng | PACO | ALNS |
|---|---|---|---|---|---|---|
| A-CH1 | 15 | 14 | 29.9 · 14 · 0 | 18.4 · 2 · 0 | 15.5 · 2 · 1 | 15.5 · 1 · 0 |
| A-CH2 | 19 | 18 | 52.9 · 18 · 0 | 26.9 · 2 · 0 | 22.0 · 2 · 2 | 22.0 · 1 · 2 |
| A-CH3 | 19 | 18 | 88.8 · 18 · 0 | 35.0 · 4 · 0 | 23.7 · 2 · 0 | 23.7 · 2 · 0 |
| A-CH4 | 22 | 21 | 72.9 · 21 · 0 | 31.4 · 4 · 0 | 19.9 · 2 · 6 | 21.1 · 2 · 4 |
| A-CH5 | 26 | 25 | 106.5 · 25 · 0 | 39.7 · 4 · 0 | 27.9 · 2 · 1 | 26.1 · 2 · 6 |
| A-CH6 | 13 | 12 | 36.7 · 12 · 0 | 25.3 · 3 · 0 | 18.3 · 2 · 1 | 18.3 · 1 · 1 |
| B-CH1 | 12 | 11 | 42.7 · 11 · 0 | 25.5 · 2 · 0 | 17.7 · 1 · 1 | 17.7 · 1 · 1 |
| B-CH2 | 12 | 11 | 49.8 · 11 · 0 | 24.2 · 2 · 0 | 17.9 · 1 · 0 | 17.9 · 1 · 0 |
| B-CH3 | 12 | 11 | 36.0 · 11 · 0 | 18.2 · 2 · 0 | 17.2 · 2 · 0 | 17.3 · 2 · 0 |
| B-CH4 | 14 | 13 | 27.8 · 13 · 0 | 13.3 · 1 · 0 | 13.3 · 2 · 0 | 13.3 · 1 · 0 |
| B-CH5 | 17 | 16 | 35.0 · 16 · 0 | 13.0 · 3 · 0 | 7.4 · 2 · 0 | 8.0 · 1 · 1 |
| C-CH1 | 23 | 22 | 59.9 · 22 · 0 | 25.3 · 3 · 0 | 18.6 · 2 · 3 | 18.5 · 2 · 1 |
| C-CH2 | 16 | 15 | 72.1 · 15 · 0 | 27.3 · 3 · 0 | 17.4 · 2 · 3 | 17.4 · 1 · 3 |
| C-CH3 | 16 | 15 | 55.6 · 15 · 0 | 24.4 · 2 · 0 | 16.4 · 2 · 0 | 16.4 · 1 · 0 |
| C-CH4 | 24 | 23 | 74.2 · 23 · 0 | 30.0 · 3 · 0 | 19.4 · 2 · 5 | 19.4 · 2 · 6 |
| C-CH5 | 14 | 13 | 47.5 · 13 · 0 | 27.5 · 4 · 0 | 17.1 · 2 · 1 | 16.9 · 1 · 0 |
| C-CH6 | 16 | 15 | 60.0 · 15 · 0 | 23.4 · 2 · 0 | 19.4 · 2 · 2 | 19.4 · 1 · 2 |
| C-CH7 | 12 | 11 | 37.5 · 11 · 0 | 17.4 · 2 · 0 | 13.7 · 1 · 0 | 13.7 · 1 · 0 |

![km per store](routing_benchmark_km.svg)

## R1 — PACO so với điều phối chia vùng (frn-v1 §6)

| Hệ số đường vòng | PACO ngắn hơn | Tổng km PACO | Tổng km chia vùng | Tiết kiệm | Trễ PACO | Trễ chia vùng |
|---|---|---|---|---|---|---|
| 1,3 (chính) | 17/18 đợt | 322,6 | 446,1 | 27,7% | 26 | 0 |
| 1,58 (độ nhạy) | 17/18 đợt | 390,9 | 542,6 | 28,0% | 36 | 0 |

**R1 KHÔNG ĐẠT / FAIL** — tiêu chí: PACO ngắn hơn ở ≥ 14/18 đợt và tổng điểm trễ không nhiều hơn, ở hệ số 1,3. Chia vùng = cách điều phối viên làm tay: quét theo hướng quanh cửa hàng, đầy xe hoặc sắp trễ thì sang chuyến mới, xe về trước nhận chuyến sau (`routing/dispatch_baseline.py`).

## R1′ — routing-PL có thời gian phục vụ (frn-v1.2, thăm dò, viết sau khi xem R1)

| Hệ số đường vòng | PACO ngắn hơn | Tổng km PACO | Tổng km chia vùng | Tiết kiệm | Trễ PACO | Trễ chia vùng |
|---|---|---|---|---|---|---|
| 1,3 (chính) | 17/18 đợt | 331,3 | 446,1 | 25,7% | 0 | 0 |
| 1,58 (độ nhạy) | 17/18 đợt | 404,1 | 542,6 | 25,5% | 0 | 0 |

**R1′ ĐẠT / PASS** — tiêu chí: PACO ngắn hơn ở ≥ 14/18 đợt và tổng điểm trễ không nhiều hơn, ở hệ số 1,3. Chia vùng = cách điều phối viên làm tay: quét theo hướng quanh cửa hàng, đầy xe hoặc sắp trễ thì sang chuyến mới, xe về trước nhận chuyến sau (`routing/dispatch_baseline.py`).
<!-- END GENERATED -->

## Phân tích (viết tay) / analysis (hand-written)

**Tiêu chí §1.4 #4 — ĐẠT / holds.** Dữ liệu dựng lại trên vị trí thật từ OpenStreetMap (cửa hàng, điểm nhận, tòa nhà
làm điểm giao) với đơn online do chương trình mở rộng từ tham số do AI (Claude Haiku 5.5) sinh
(`GEN_FROM_AI_PARAMS_V1`; `docs/data-provenance.md`) — không phải đơn thật. Trên 18 đợt (302 đơn, 18 đơn bị loại
trước khi định tuyến, **284 đơn được định tuyến**), PACO đi **322,6 km so với 985,7 km** của "mỗi đơn một chuyến"
(**−67,3%**, từng đợt −48,2% đến −78,8%) với **33 xe so với 284 chuyến**, tốt hơn cả km lẫn số xe ở 18/18 đợt.

**R1 (frn-v1 §6, đăng ký trước) — KHÔNG ĐẠT.** So với cách điều phối viên chia vùng bằng tay (`zone_sweep`: 446,1 km,
48 chuyến, 0 trễ), PACO ngắn hơn ở 17/18 đợt (−27,7% km) nhưng có **26 điểm giao trễ** (ở 11/18 đợt), nên trượt vế
thứ hai của tiêu chí. **Nguyên nhân (đọc mã):** các bộ giải mã của routing-PL tăng đồng hồ bằng
`max(giờ đến, giờ mở)` và không cộng thời gian giao tại điểm, dù instance có ghi (3 phút/đơn ở FreshMesh); tuyến
của PACO chỉ đúng giờ nếu giao hàng mất 0 phút. FreshMesh tính lại giờ đến có thời gian giao nên báo các điểm đó
trễ — đây là trễ thật khi chạy ngoài đường, không phải lỗi đo.

**R1′ (frn-v1.2, viết sau khi xem R1, trước khi chạy) — ĐẠT, thăm dò.** Với bản vá
`routing/solver-patches/0001-routing-pl-service-time.patch` (cộng thời gian giao sau mỗi điểm, ở mọi bộ giải mã),
PACO đi 331,3 km (+2,7% so với trước khi vá), vẫn ngắn hơn chia vùng ở 17/18 đợt (**−25,7%**), với **0 điểm trễ**;
hệ số đường vòng 1,58 cho cùng kết luận (−25,5%, 0 trễ). Submodule routing-PL không bị sửa: ảnh solver được dựng
bằng `routing/solver.Dockerfile`, áp bản vá lên commit đã ghim. Bản vá nên được đưa về kho routing-PL gốc.

- **Giả định hệ số đường vòng:** km/giờ đến tính bằng 20 km/h × hệ số 1,3 trên khoảng cách đường chim bay. Phép đo
  OSRM (hồ sơ ô tô) cho trung vị 1,58 (IQR 1,40–1,99, `docs/data-real-detour.md`); xe máy chưa đo. Bảng R1/R1′ có
  thêm lần chạy ở 1,58: tỷ lệ tiết kiệm gần như không đổi, số điểm trễ trước khi vá tăng (36).
- **"Mỗi đơn một chuyến" có 0 trễ do cách định nghĩa** (mỗi đơn một xe đi thẳng từ phút 0, 11–25 chuyến/đợt với đội
  4 xe). "Chia vùng" dùng đúng đội 4 xe, chuyến sau xuất phát khi xe về, nên là baseline thực tế hơn.
- **ALNS** (qua `docker exec … --solver alns`, chưa vá, lần chạy trước): 322,3 km, 24 xe, 27 điểm trễ; so với PACO
  (chưa vá) ngắn hơn ở 3 đợt, dài hơn ở 4, bằng ở 11. ALNS dùng cùng bộ giải mã nên cũng chịu lỗi thời gian giao.
- **SA — không có số:** binary SA của routing-PL dừng với `std::out_of_range` (`customer2node` trong `Solver.cpp`)
  trên instance FreshMesh (API và CLI, small và medium), nên không nằm trong benchmark mặc định.
- **Runtime:** thời gian solver tự báo, giải mới ở mọi đợt (`cached` = 0). Lần chạy PACO này trung bình 5,1 s/đợt
  (2,5–11,9 s) trên máy chủ dùng chung đang chạy thí nghiệm khác; bản đã vá chạy trong container giới hạn 1 CPU,
  14,4 s/đợt. ALNS 2,0 s/đợt ở lần chạy trước. Giải tuần tự để không tranh solver với API.

**English.** On the 18 demo batches (real OSM sites; program-expanded orders, not real ones; 284 routed orders) PACO
drives 322.6 km vs 985.7 km for one-trip-per-order (−67.3%) with 33 vehicles vs 284 trips, better on both in 18/18
batches (§1.4 #4 holds). **R1 (pre-registered) fails:** against hand-made dispatcher zones (`zone_sweep`, 446.1 km,
0 late) PACO is shorter in 17/18 batches (−27.7%) but has 26 late stops. Cause: routing-PL's decoders advance the
clock as max(arrival, earliest) and never add the stop's service time, so PACO's routes are on time only with
0-minute hand-overs. **R1′ (frn-v1.2, written after R1 and before its run) passes:** with the service-time patch
PACO drives 331.3 km (+2.7%), still shorter than the zones in 17/18 batches (−25.7%), with 0 late stops; detour 1.58
gives the same conclusion. The submodule is not modified: the solver image applies the patch at build time
(`routing/solver.Dockerfile`); the fix should go upstream to routing-PL. ALNS (unpatched, earlier run): 322.3 km,
24 vehicles, 27 late stops. SA is not reported (`std::out_of_range` crash). Detour 1.3 is not supported by the OSRM
car-profile measurement (median 1.58), so absolute km are likely understated; savings ratios barely move at 1.58.
