<!-- BEGIN GENERATED -->
# Sim30 — kết quả mô phỏng 30 ngày / 30-day inventory simulation results

Dữ liệu: **SIMULATED**. Giao thức đăng ký trước: [sim30-protocol.md](sim30-protocol.md) (`sim30-v1`, revision `sim30-v2`). Seeds 1001, 1002, 1003, 1004, 1005; mean [95% t-CI] over seeds; % pooled over stores × 14 fresh SKUs × 30 days.

## Kết luận theo tiêu chí §1.4 #3 / Verdict

| Chuỗi / chain | v1: Cân bằng h=1 (pre-registered) | v2: carry 20% (revision) |
|---|---|---|
| CHAIN_A | **KHÔNG ĐẠT / FAIL** — Δbỏ 4.61 [4.23; 5.00] pp; Δhết hàng -12.31 [-13.74; -10.88] pp | **ĐẠT / PASS** — Δbỏ -3.02 [-3.10; -2.93] pp; Δhết hàng -5.87 [-6.75; -4.99] pp |
| CHAIN_B | **KHÔNG ĐẠT / FAIL** — Δbỏ 7.67 [6.56; 8.79] pp; Δhết hàng -22.27 [-22.48; -22.06] pp | **ĐẠT / PASS** — Δbỏ -4.38 [-5.30; -3.47] pp; Δhết hàng -14.05 [-14.66; -13.43] pp |
| CHAIN_C | **KHÔNG ĐẠT / FAIL** — Δbỏ 9.42 [8.90; 9.94] pp; Δhết hàng -14.50 [-15.25; -13.76] pp | **ĐẠT / PASS** — Δbỏ -3.35 [-3.68; -3.02] pp; Δhết hàng -5.05 [-5.89; -4.22] pp |

Toàn bộ / overall (all chains pass): `sim30-v1` → KHÔNG ĐẠT / FAIL; `sim30-v2` → ĐẠT / PASS.

Rule: chain passes iff upper 95% CI of Δwaste < 0 **and** upper 95% CI of Δstockout ≤ +2.0 pp (Δ = FreshMesh − baseline_mean7).

## Bảng kết quả / results by policy

| Chuỗi | Chính sách / policy | % bỏ / waste % | % hết hàng / stockout % | Lợi nhuận / net profit (triệu đ) | Chi phí proxy (triệu đ) |
|---|---|---|---|---|---|
| CHAIN_A | FreshMesh Cân bằng h=1 (v1 primary) | 13.2 [12.6; 13.9] | 5.3 [5.0; 5.6] | 235.8 [222.0; 249.5] | 136.3 [129.6; 142.9] |
| CHAIN_A | FreshMesh Cân bằng h=L (exploratory) | 15.5 [14.7; 16.3] | 5.2 [4.9; 5.4] | 228.8 [214.0; 243.7] | 143.3 [135.5; 151.0] |
| CHAIN_A | FreshMesh An toàn h=1 (exploratory) | 20.2 [19.6; 20.8] | 1.2 [1.0; 1.4] | 179.0 [164.0; 194.1] | 182.2 [176.0; 188.4] |
| CHAIN_A | FreshMesh Tiết kiệm h=1 (exploratory) | 4.7 [4.3; 5.1] | 17.9 [16.8; 19.0] | 264.6 [258.2; 271.0] | 134.9 [125.5; 144.3] |
| CHAIN_A | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | 5.6 [5.1; 6.1] | 11.7 [10.9; 12.6] | 279.0 [269.9; 288.1] | 108.8 [101.7; 115.9] |
| CHAIN_A | Baseline TB 7 ngày / mean-7 | 8.6 [8.1; 9.2] | 17.6 [16.2; 19.0] | 241.8 [231.9; 251.8] | 154.6 [146.7; 162.5] |
| CHAIN_A | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | 4.4 [4.1; 4.7] | 36.0 [34.8; 37.1] | 208.2 [202.7; 213.6] | 224.8 [211.0; 238.6] |
| CHAIN_B | FreshMesh Cân bằng h=1 (v1 primary) | 23.8 [22.5; 25.0] | 7.2 [6.9; 7.5] | 69.2 [63.7; 74.7] | 104.0 [102.3; 105.7] |
| CHAIN_B | FreshMesh Cân bằng h=L (exploratory) | 22.8 [21.6; 23.9] | 7.8 [7.6; 8.1] | 79.2 [73.5; 84.9] | 95.0 [93.4; 96.6] |
| CHAIN_B | FreshMesh An toàn h=1 (exploratory) | 31.0 [29.8; 32.1] | 1.8 [1.5; 2.2] | 37.8 [31.6; 44.0] | 128.7 [125.5; 132.0] |
| CHAIN_B | FreshMesh Tiết kiệm h=1 (exploratory) | 10.3 [9.6; 10.9] | 20.8 [19.5; 22.0] | 105.0 [101.6; 108.4] | 82.2 [79.4; 85.0] |
| CHAIN_B | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | 11.7 [10.9; 12.5] | 15.4 [14.8; 16.1] | 108.6 [104.6; 112.6] | 73.6 [71.7; 75.4] |
| CHAIN_B | Baseline TB 7 ngày / mean-7 | 16.1 [14.9; 17.3] | 29.5 [29.2; 29.8] | 76.0 [73.2; 78.8] | 120.4 [115.4; 125.3] |
| CHAIN_B | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | 8.7 [7.7; 9.7] | 51.5 [50.1; 52.8] | 65.2 [63.3; 67.1] | 150.7 [143.1; 158.4] |
| CHAIN_C | FreshMesh Cân bằng h=1 (v1 primary) | 20.1 [18.5; 21.7] | 8.8 [8.0; 9.6] | 219.9 [179.6; 260.1] | 382.6 [373.9; 391.4] |
| CHAIN_C | FreshMesh Cân bằng h=L (exploratory) | 16.9 [15.2; 18.6] | 9.6 [8.8; 10.5] | 298.6 [258.9; 338.2] | 308.2 [303.3; 313.1] |
| CHAIN_C | FreshMesh An toàn h=1 (exploratory) | 26.2 [24.6; 27.8] | 2.5 [2.0; 3.0] | 98.6 [51.7; 145.5] | 479.4 [465.6; 493.1] |
| CHAIN_C | FreshMesh Tiết kiệm h=1 (exploratory) | 4.9 [4.2; 5.7] | 30.1 [27.9; 32.2] | 351.8 [336.1; 367.6] | 316.1 [284.0; 348.1] |
| CHAIN_C | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | 7.3 [6.3; 8.4] | 18.3 [16.9; 19.7] | 385.9 [360.0; 411.7] | 250.2 [232.3; 268.0] |
| CHAIN_C | Baseline TB 7 ngày / mean-7 | 10.7 [9.5; 11.9] | 23.3 [22.2; 24.5] | 324.1 [296.5; 351.7] | 323.3 [302.7; 343.9] |
| CHAIN_C | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | 5.1 [4.5; 5.6] | 45.4 [43.8; 46.9] | 275.6 [259.1; 292.0] | 435.8 [400.6; 471.1] |

## Chênh lệch so với baseline / paired difference vs `baseline_mean7`

| Chuỗi | Chính sách | Δ % bỏ (pp) | Δ % hết hàng (pp) | Δ lợi nhuận (triệu đ) |
|---|---|---|---|---|
| CHAIN_A | FreshMesh Cân bằng h=1 (v1 primary) | 4.61 [4.23; 5.00] | -12.31 [-13.74; -10.88] | -6.1 [-15.3; 3.2] |
| CHAIN_A | FreshMesh Cân bằng h=L (exploratory) | 6.86 [6.22; 7.50] | -12.44 [-13.85; -11.03] | -13.0 [-23.5; -2.4] |
| CHAIN_A | FreshMesh An toàn h=1 (exploratory) | 11.55 [11.17; 11.94] | -16.38 [-17.68; -15.09] | -62.8 [-72.6; -53.0] |
| CHAIN_A | FreshMesh Tiết kiệm h=1 (exploratory) | -3.94 [-4.08; -3.80] | 0.28 [-0.55; 1.11] | 22.7 [18.3; 27.2] |
| CHAIN_A | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | -3.02 [-3.10; -2.93] | -5.87 [-6.75; -4.99] | 37.1 [32.7; 41.6] |
| CHAIN_A | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | -4.27 [-4.75; -3.79] | 18.38 [17.57; 19.19] | -33.7 [-40.5; -26.8] |
| CHAIN_B | FreshMesh Cân bằng h=1 (v1 primary) | 7.67 [6.56; 8.79] | -22.27 [-22.48; -22.06] | -6.8 [-11.8; -1.7] |
| CHAIN_B | FreshMesh Cân bằng h=L (exploratory) | 6.68 [5.58; 7.77] | -21.64 [-21.89; -21.39] | 3.2 [-2.2; 8.7] |
| CHAIN_B | FreshMesh An toàn h=1 (exploratory) | 14.86 [13.75; 15.97] | -27.65 [-27.99; -27.31] | -38.2 [-44.5; -31.8] |
| CHAIN_B | FreshMesh Tiết kiệm h=1 (exploratory) | -5.85 [-6.81; -4.88] | -8.72 [-10.12; -7.32] | 29.0 [25.5; 32.4] |
| CHAIN_B | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | -4.38 [-5.30; -3.47] | -14.05 [-14.66; -13.43] | 32.6 [28.8; 36.4] |
| CHAIN_B | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | -7.43 [-8.30; -6.56] | 21.97 [20.96; 22.99] | -10.8 [-13.3; -8.2] |
| CHAIN_C | FreshMesh Cân bằng h=1 (v1 primary) | 9.42 [8.90; 9.94] | -14.50 [-15.25; -13.76] | -104.2 [-126.2; -82.3] |
| CHAIN_C | FreshMesh Cân bằng h=L (exploratory) | 6.22 [5.51; 6.94] | -13.68 [-14.38; -12.98] | -25.5 [-44.8; -6.2] |
| CHAIN_C | FreshMesh An toàn h=1 (exploratory) | 15.55 [15.03; 16.08] | -20.80 [-21.78; -19.83] | -225.5 [-251.7; -199.2] |
| CHAIN_C | FreshMesh Tiết kiệm h=1 (exploratory) | -5.74 [-6.46; -5.01] | 6.75 [5.30; 8.20] | 27.7 [15.6; 39.9] |
| CHAIN_C | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | -3.35 [-3.68; -3.02] | -5.05 [-5.89; -4.22] | 61.8 [55.3; 68.3] |
| CHAIN_C | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | -5.61 [-6.60; -4.62] | 22.05 [21.47; 22.63] | -48.5 [-61.8; -35.3] |

![waste and stockout](sim30_waste_stockout.svg)
<!-- END GENERATED -->

## Phân tích (viết tay) / analysis (hand-written)

**Tóm tắt tiếng Việt.**
- Theo giao thức đăng ký trước `sim30-v1` (FreshMesh dùng đúng cấu hình mặc định của API: phương án
  *Cân bằng*, `horizon_days = 1`, chi phí lưu kho 0,5%/đêm), **tiêu chí §1.4 #3 KHÔNG ĐẠT ở cả 3 chuỗi**:
  FreshMesh bỏ nhiều hàng hơn baseline (+4,6 / +7,7 / +9,4 điểm %), đổi lại hết hàng ít hơn rất nhiều
  (−12,3 / −22,3 / −14,5 điểm %). Lợi nhuận thấp hơn baseline ở B và C (C: −104 triệu đ / 30 ngày); ở A
  khoảng tin cậy chứa 0.
- Nguyên nhân (chẩn đoán trên seed thử 999, trước khi chạy seed xác nhận): với `horizon_days = 1`, mô hình chi
  phí của `plan_inventory` coi phần dư của lô **mới** hạn 2–3 ngày chỉ tốn chi phí lưu kho 0,5% giá vốn, trong
  khi thiếu 1 đơn vị tốn biên lợi nhuận + phạt. Nên phương án Cân bằng nhập gần phân vị 99,5% cho hàng hạn
  2–3 ngày (seed 999, CHAIN_A: hàng hạn 2 ngày bỏ 16,0% / hết 1,2%, baseline 7,7% / 18,4%). Hàng hạn 1 ngày
  là bài toán newsvendor chuẩn (tỷ lệ tới hạn 0,44–0,53) nên hết hàng cao (~28%). Ngoài ra dự báo P50 thấp hơn
  nhu cầu thực khoảng 9% trên seed 999 (doanh số bị cắt khi hết hàng được ghi lại làm lịch sử, mô hình không
  biết khuyến mãi tương lai, không huấn luyện lại).
- Bản sửa `sim30-v2` (ghi vào giao thức **trước** khi chạy seed xác nhận, chọn trên seed 999 theo lợi nhuận
  tối đa, không theo luật đạt/không đạt): thêm chi phí rủi ro mang hàng tươi qua đêm 20% giá vốn
  (`Constraints.holding_cost_rate_per_day = 0,20`). Kết quả trên 5 seed xác nhận: **ĐẠT ở cả 3 chuỗi** — bỏ
  ít hơn 3,0 / 4,4 / 3,4 điểm %, hết hàng ít hơn 5,9 / 14,1 / 5,1 điểm %, lợi nhuận cao hơn 37 / 33 / 62 triệu đ
  trong 30 ngày.
- Cách đọc trung thực: kết quả chính thức (đăng ký trước) là **v1 không đạt**. v2 đạt nhưng là bản sửa tham
  số sau khi thấy kết quả seed thử của v1; ngưỡng +2 điểm %, seed và luật không đổi. Khi chạy thí nghiệm, cấu hình
  mặc định của API là 0,5%/đêm; sau đó mặc định sản xuất đã được đổi sang 20%/đêm cho hàng tươi (xem ghi chú
  "Cập nhật sản xuất" ở cuối tệp).

**English summary.**
- Pre-registered `sim30-v1` (FreshMesh exactly as the API runs it: *Cân bằng*, `horizon_days = 1`, 0.5%/night
  holding) **fails §1.4 #3 on all three chains**: more waste than the 7-day-mean baseline (+4.6 / +7.7 /
  +9.4 pp) in exchange for far fewer stockouts (−12.3 / −22.3 / −14.5 pp). It sits at a different point of the
  waste–stockout trade-off rather than dominating the baseline; net profit is lower in B and C.
- Cause (diagnosed on dev seed 999 only): the one-day horizon prices the leftover of a *new* 2–3-day lot at the
  0.5% holding cost, so Cân bằng orders near the 99.5% demand quantile for those SKUs; 1-day SKUs follow the
  newsvendor ratio (0.44–0.53) and stock out ~28%; P50 under-forecasts realised demand by ~9% on the dev seed
  (censored sales fed back as history, promo-blind future, no refit). The horizon-L arm does not fix it.
- Revision `sim30-v2` (written before any confirmatory run; parameter picked on the dev seed by maximum total
  profit): overnight carry-over risk cost 20% of unit cost for fresh SKUs. On the 5 confirmatory seeds it
  **passes on all three chains** (waste −3.0 / −4.4 / −3.4 pp, stockout −5.9 / −14.1 / −5.1 pp, profit
  +37 / +33 / +62 M VND per 30 days).
- Exploratory: *Tiết kiệm* also cuts waste everywhere but raises stockouts by +6.8 pp in CHAIN_C (would fail);
  the order-up-to baseline (`mean7_net`) wastes least in A and B but loses 36–52% of demand.

**Giới hạn / limitations.** Dữ liệu giả lập, cùng bộ sinh với dữ liệu huấn luyện (chỉ đổi seed nhiễu); mô hình
không huấn luyện lại; lead time 0; không có ràng buộc ngân sách/kho lạnh; không mô phỏng giảm giá cận hạn hay
điều chuyển (sẽ giảm thêm hàng bỏ); baseline bỏ qua tồn kho đúng như mô tả trong spec nên hết hàng 18–30%.

## Cập nhật sản xuất / Production note

Sau thí nghiệm này, mặc định của `decision.Constraints.fresh_carry_cost_rate_per_day` được đặt là `0.20` (revision sim30-v2) cho hàng có hạn dùng ≤ 3 ngày, nên API/CLI hiện chạy đúng cấu hình v2. Kết quả v1 (đăng ký trước) vẫn được giữ nguyên ở trên: **v1 không đạt** tiêu chí #3; v2 đạt trên cả 3 chuỗi nhưng là bản điều chỉnh sau khi biết kết quả debug, không phải kiểm định đăng ký trước.
After this experiment the production default `Constraints.fresh_carry_cost_rate_per_day` is `0.20` (revision sim30-v2) for items with shelf life ≤ 3 days, so the API/CLI now run the v2 configuration. The pre-registered v1 result stays above: v1 **failed** criterion #3; v2 passes on all three chains but is a post-hoc revision, not a pre-registered test.

### Production adoption (2026-10-13) — erratum to the protocol wording

`sim30-protocol.md` is frozen and its SHA-256 is pinned in every row of `sim30_results.csv` (checked by
`tests/simulation/test_demand_protocol.py`), so it is **not** edited; two of its sentences are outdated and
are corrected here instead:

- Revision `sim30-v2` says *"No change to `decision/`"*. That was true for the experiment (the arm only set a
  `Constraints` field), but afterwards `decision/` **was** changed for production: a new field
  `Constraints.fresh_carry_cost_rate_per_day` (default `0.20`, items with shelf life ≤ 3 days) is used by
  `plan_inventory`, and its value is stated in the user-facing `assumptions_vi`.
- §3 describes `freshmesh_balanced_h1` (v1) as using the economics "exactly as the API" with the production
  default. Since the adoption the API runs the **v2** configuration; the v1 arm reproduces the *old* API
  explicitly (`simulation/freshmesh.py`, `holding_rate=0.005` passed as both the holding and the fresh
  carry rate). Threshold, seeds, metrics and success rule are unchanged; the v1 result remains the
  pre-registered headline.
