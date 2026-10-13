<!-- BEGIN GENERATED -->
# Sim30 — kết quả mô phỏng 30 ngày / 30-day inventory simulation results

Nguồn dữ liệu: **Lịch nghỉ lễ Việt Nam theo văn bản pháp luật + âm lịch; Mô phỏng bằng chương trình (tham số giả định); © OpenStreetMap contributors (ODbL); Vị trí thật từ OpenStreetMap (ODbL), gán chuỗi bằng chương trình; Lượng mưa ngày TP.HCM — Open-Meteo Historical Weather API (CC BY 4.0); Dự báo mưa TP.HCM — Open-Meteo Forecast API (CC BY 4.0)**. Giao thức đăng ký trước: [sim30-protocol.md](sim30-protocol.md) (`sim30-v1`, revision `sim30-v2`). Seeds 1001, 1002, 1003, 1004, 1005; mean [95% t-CI] over seeds; % pooled over stores × 14 fresh SKUs × 30 days.

## Kết luận theo tiêu chí §1.4 #3 / Verdict

| Chuỗi / chain | v1: Cân bằng h=1 (pre-registered) | v2: carry 20% (revision) |
|---|---|---|
| CHAIN_A | **KHÔNG ĐẠT / FAIL** — Δbỏ 4.22 [3.82; 4.63] pp; Δhết hàng -11.23 [-12.36; -10.09] pp | **ĐẠT / PASS** — Δbỏ -3.34 [-3.77; -2.91] pp; Δhết hàng -5.14 [-6.16; -4.12] pp |
| CHAIN_B | **KHÔNG ĐẠT / FAIL** — Δbỏ 7.12 [6.49; 7.75] pp; Δhết hàng -22.17 [-25.55; -18.79] pp | **ĐẠT / PASS** — Δbỏ -4.56 [-5.27; -3.86] pp; Δhết hàng -13.11 [-16.78; -9.45] pp |
| CHAIN_C | **KHÔNG ĐẠT / FAIL** — Δbỏ 8.90 [8.06; 9.74] pp; Δhết hàng -14.59 [-16.23; -12.95] pp | **ĐẠT / PASS** — Δbỏ -3.35 [-3.54; -3.16] pp; Δhết hàng -4.42 [-5.54; -3.30] pp |

Toàn bộ / overall (all chains pass): `sim30-v1` → KHÔNG ĐẠT / FAIL; `sim30-v2` → ĐẠT / PASS.

Rule: chain passes iff upper 95% CI of Δwaste < 0 **and** upper 95% CI of Δstockout ≤ +2.0 pp (Δ = FreshMesh − baseline_mean7).

## Bảng kết quả / results by policy

| Chuỗi | Chính sách / policy | % bỏ / waste % | % hết hàng / stockout % | Lợi nhuận / net profit (triệu đ) | Chi phí proxy (triệu đ) |
|---|---|---|---|---|---|
| CHAIN_A | FreshMesh Cân bằng h=1 (v1 primary) | 12.7 [12.2; 13.3] | 5.6 [5.3; 5.8] | 250.0 [241.7; 258.4] | 143.8 [142.0; 145.7] |
| CHAIN_A | FreshMesh Cân bằng h=L (exploratory) | 15.4 [14.8; 15.9] | 5.4 [5.3; 5.5] | 237.6 [227.1; 248.1] | 156.4 [153.0; 159.7] |
| CHAIN_A | FreshMesh An toàn h=1 (exploratory) | 19.4 [19.0; 19.9] | 1.3 [1.1; 1.5] | 189.8 [181.6; 198.1] | 192.6 [190.8; 194.4] |
| CHAIN_A | FreshMesh Tiết kiệm h=1 (exploratory) | 4.4 [4.0; 4.7] | 18.1 [17.4; 18.8] | 282.0 [277.3; 286.6] | 140.0 [134.5; 145.6] |
| CHAIN_A | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | 5.2 [4.9; 5.5] | 11.6 [11.2; 12.1] | 298.1 [291.2; 304.9] | 111.1 [107.0; 115.1] |
| CHAIN_A | Baseline TB 7 ngày / mean-7 | 8.5 [7.9; 9.1] | 16.8 [15.4; 18.1] | 257.9 [250.2; 265.6] | 160.7 [154.9; 166.4] |
| CHAIN_A | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | 4.1 [3.9; 4.3] | 35.2 [33.9; 36.6] | 224.3 [219.3; 229.3] | 232.2 [224.5; 239.8] |
| CHAIN_B | FreshMesh Cân bằng h=1 (v1 primary) | 21.6 [20.8; 22.4] | 7.6 [7.0; 8.1] | 78.3 [73.6; 83.1] | 101.7 [99.1; 104.2] |
| CHAIN_B | FreshMesh Cân bằng h=L (exploratory) | 20.1 [19.2; 21.0] | 8.3 [7.7; 8.9] | 89.7 [86.7; 92.7] | 91.5 [89.8; 93.1] |
| CHAIN_B | FreshMesh An toàn h=1 (exploratory) | 28.5 [27.8; 29.1] | 2.1 [1.8; 2.4] | 48.4 [43.2; 53.5] | 124.9 [122.4; 127.4] |
| CHAIN_B | FreshMesh Tiết kiệm h=1 (exploratory) | 8.5 [7.8; 9.2] | 24.3 [23.4; 25.2] | 107.5 [105.3; 109.6] | 89.8 [86.0; 93.6] |
| CHAIN_B | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | 9.9 [9.1; 10.6] | 16.6 [16.4; 16.8] | 114.7 [111.4; 118.1] | 75.5 [73.3; 77.8] |
| CHAIN_B | Baseline TB 7 ngày / mean-7 | 14.4 [13.7; 15.2] | 29.7 [26.1; 33.3] | 84.3 [78.4; 90.3] | 118.9 [108.3; 129.5] |
| CHAIN_B | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | 7.2 [6.5; 7.8] | 53.3 [50.4; 56.2] | 66.6 [61.9; 71.2] | 159.9 [152.4; 167.4] |
| CHAIN_C | FreshMesh Cân bằng h=1 (v1 primary) | 18.5 [17.0; 20.0] | 8.6 [7.9; 9.3] | 247.5 [214.5; 280.6] | 368.2 [360.7; 375.6] |
| CHAIN_C | FreshMesh Cân bằng h=L (exploratory) | 15.5 [13.8; 17.1] | 9.6 [8.9; 10.3] | 319.1 [285.0; 353.3] | 300.9 [292.9; 308.8] |
| CHAIN_C | FreshMesh An toàn h=1 (exploratory) | 24.7 [23.2; 26.2] | 2.8 [2.5; 3.1] | 120.9 [80.4; 161.5] | 472.4 [459.0; 485.8] |
| CHAIN_C | FreshMesh Tiết kiệm h=1 (exploratory) | 4.0 [3.4; 4.6] | 30.9 [29.4; 32.4] | 364.0 [352.8; 375.2] | 320.6 [294.9; 346.2] |
| CHAIN_C | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | 6.3 [5.4; 7.1] | 18.8 [17.9; 19.7] | 401.7 [382.7; 420.7] | 249.7 [235.3; 264.1] |
| CHAIN_C | Baseline TB 7 ngày / mean-7 | 9.6 [8.9; 10.3] | 23.2 [21.6; 24.8] | 342.0 [327.4; 356.5] | 316.8 [288.8; 344.9] |
| CHAIN_C | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | 4.3 [4.0; 4.6] | 44.7 [43.3; 46.0] | 289.6 [278.1; 301.2] | 435.6 [402.1; 469.1] |

## Chênh lệch so với baseline / paired difference vs `baseline_mean7`

| Chuỗi | Chính sách | Δ % bỏ (pp) | Δ % hết hàng (pp) | Δ lợi nhuận (triệu đ) |
|---|---|---|---|---|
| CHAIN_A | FreshMesh Cân bằng h=1 (v1 primary) | 4.22 [3.82; 4.63] | -11.23 [-12.36; -10.09] | -7.9 [-13.5; -2.2] |
| CHAIN_A | FreshMesh Cân bằng h=L (exploratory) | 6.87 [6.57; 7.17] | -11.38 [-12.64; -10.12] | -20.4 [-26.4; -14.3] |
| CHAIN_A | FreshMesh An toàn h=1 (exploratory) | 10.92 [10.51; 11.33] | -15.49 [-16.63; -14.34] | -68.1 [-73.6; -62.6] |
| CHAIN_A | FreshMesh Tiết kiệm h=1 (exploratory) | -4.16 [-4.66; -3.67] | 1.32 [0.46; 2.17] | 24.0 [19.9; 28.2] |
| CHAIN_A | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | -3.34 [-3.77; -2.91] | -5.14 [-6.16; -4.12] | 40.2 [36.3; 44.1] |
| CHAIN_A | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | -4.44 [-4.86; -4.01] | 18.46 [17.84; 19.08] | -33.6 [-37.5; -29.7] |
| CHAIN_B | FreshMesh Cân bằng h=1 (v1 primary) | 7.12 [6.49; 7.75] | -22.17 [-25.55; -18.79] | -6.0 [-12.3; 0.4] |
| CHAIN_B | FreshMesh Cân bằng h=L (exploratory) | 5.66 [5.19; 6.12] | -21.44 [-25.07; -17.81] | 5.4 [-0.0; 10.8] |
| CHAIN_B | FreshMesh An toàn h=1 (exploratory) | 14.02 [13.38; 14.67] | -27.64 [-31.19; -24.09] | -36.0 [-43.6; -28.3] |
| CHAIN_B | FreshMesh Tiết kiệm h=1 (exploratory) | -5.95 [-6.39; -5.51] | -5.42 [-8.61; -2.22] | 23.2 [18.9; 27.4] |
| CHAIN_B | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | -4.56 [-5.27; -3.86] | -13.11 [-16.78; -9.45] | 30.4 [25.0; 35.8] |
| CHAIN_B | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | -7.28 [-7.65; -6.91] | 23.53 [20.50; 26.57] | -17.8 [-23.4; -12.1] |
| CHAIN_C | FreshMesh Cân bằng h=1 (v1 primary) | 8.90 [8.06; 9.74] | -14.59 [-16.23; -12.95] | -94.4 [-119.5; -69.3] |
| CHAIN_C | FreshMesh Cân bằng h=L (exploratory) | 5.87 [4.87; 6.88] | -13.64 [-15.24; -12.03] | -22.8 [-49.9; 4.2] |
| CHAIN_C | FreshMesh An toàn h=1 (exploratory) | 15.09 [14.19; 15.99] | -20.42 [-21.92; -18.92] | -221.0 [-254.0; -188.1] |
| CHAIN_C | FreshMesh Tiết kiệm h=1 (exploratory) | -5.59 [-5.98; -5.19] | 7.68 [6.92; 8.43] | 22.0 [16.4; 27.7] |
| CHAIN_C | FreshMesh Cân bằng h=1, carry 20% (v2 primary) | -3.35 [-3.54; -3.16] | -4.42 [-5.54; -3.30] | 59.8 [49.9; 69.6] |
| CHAIN_C | Baseline TB 7 ngày trừ tồn / mean-7 net (exploratory) | -5.29 [-5.88; -4.69] | 21.44 [20.79; 22.08] | -52.3 [-57.8; -46.9] |

![waste and stockout](sim30_waste_stockout.svg)
<!-- END GENERATED -->

## Phân tích (viết tay) / analysis (hand-written)

**Hai lần chạy cùng một giao thức / two runs of the same protocol.** Giao thức đăng ký trước đã được chạy hai lần:
lần đầu trên dữ liệu do chương trình sinh toàn bộ (phiên bản trước), và lần này (tài liệu này) sau khi lớp dữ liệu được
dựng lại trên vị trí cửa hàng thật từ OpenStreetMap, lượng mưa thật (Open-Meteo) và lịch nghỉ lễ Việt Nam thật
(`docs/data-provenance.md`); doanh số, giá, khuyến mãi và tồn kho vẫn do chương trình sinh (`GEN_PROGRAM_V1`).
Tệp giao thức, ngưỡng (+2 điểm %), seed (1001–1005), chỉ số và luật đạt/không đạt **không đổi** giữa hai lần:
SHA-256 của `sim30-protocol.md` là `498a283f…1b33fb` ở cả hai lần (cột `protocol_sha256` của CSV cũ và CSV mới).
Tham số v2 (20%) được chọn một lần trên seed thử 999 ở lần chạy đầu và **không** chọn lại trên dữ liệu mới.
The pre-registered protocol was run twice: first on the earlier fully program-generated data, and again (this
document) after the data layer was rebuilt on real OSM sites, Open-Meteo rainfall and Vietnamese holidays (sales,
prices, promotions and lots are still program-generated). The protocol file, threshold, seeds, metrics and rule
were unchanged between the two runs (same `protocol_sha256` in the old and new CSV); the v2 parameter was picked
once, on dev seed 999 of the first run, and not re-tuned on the new data.

**Tóm tắt tiếng Việt.**
- Theo giao thức đăng ký trước `sim30-v1` (FreshMesh dùng cấu hình API cũ: phương án *Cân bằng*,
  `horizon_days = 1`, chi phí lưu kho 0,5%/đêm), **tiêu chí §1.4 #3 KHÔNG ĐẠT ở cả 3 chuỗi** (A, B, C):
  FreshMesh bỏ nhiều hàng hơn baseline (+4,2 / +7,1 / +8,9 điểm %), đổi lại hết hàng ít hơn rất nhiều
  (−11,2 / −22,2 / −14,6 điểm %). Lợi nhuận thấp hơn baseline ở A (−7,9 [−13,5; −2,2] triệu đ) và C
  (−94 triệu đ / 30 ngày); ở B khoảng tin cậy chứa 0 (−6,0 [−12,3; 0,4]).
- Nguyên nhân (chẩn đoán trên seed thử 999 ở lần chạy đầu, trước khi chạy seed xác nhận; số liệu chẩn đoán dưới
  đây là của dữ liệu cũ, chưa đo lại trên dữ liệu mới): với `horizon_days = 1`, mô hình chi phí của
  `plan_inventory` coi phần dư của lô **mới** hạn 2–3 ngày chỉ tốn chi phí lưu kho 0,5% giá vốn, trong khi thiếu
  1 đơn vị tốn biên lợi nhuận + phạt. Nên phương án Cân bằng nhập gần phân vị 99,5% cho hàng hạn 2–3 ngày
  (seed 999, CHAIN_A: hàng hạn 2 ngày bỏ 16,0% / hết 1,2%, baseline 7,7% / 18,4%). Hàng hạn 1 ngày là bài toán
  newsvendor chuẩn (tỷ lệ tới hạn 0,44–0,53) nên hết hàng cao (~28%). Ngoài ra dự báo P50 thấp hơn nhu cầu thực
  khoảng 9% trên seed 999 (doanh số bị cắt khi hết hàng được ghi lại làm lịch sử, mô hình không biết khuyến mãi
  tương lai, không huấn luyện lại). Kết quả lần này cùng chiều với cơ chế đó: bỏ nhiều hơn, hết hàng ít hơn.
- Bản sửa `sim30-v2` (ghi vào giao thức **trước** khi chạy seed xác nhận lần đầu, chọn trên seed 999 theo lợi
  nhuận tối đa, không theo luật đạt/không đạt): thêm chi phí rủi ro mang hàng tươi qua đêm 20% giá vốn
  (`fresh_carry_cost_rate_per_day = 0,20`). Kết quả trên 5 seed xác nhận: **ĐẠT ở cả 3 chuỗi** — bỏ ít hơn
  3,3 / 4,6 / 3,3 điểm %, hết hàng ít hơn 5,1 / 13,1 / 4,4 điểm %, lợi nhuận cao hơn 40 / 30 / 60 triệu đ
  trong 30 ngày (khoảng tin cậy 95% của cả ba chỉ số đều không chứa 0).
- Cách đọc trung thực: kết quả chính thức (đăng ký trước) là **v1 không đạt** — giống lần chạy đầu. v2 đạt nhưng
  là bản sửa tham số sau khi thấy kết quả seed thử của v1; ngưỡng +2 điểm %, seed và luật không đổi. Mặc định sản
  xuất hiện là v2 (`fresh_carry_cost_rate_per_day = 0,20`, xem "Cập nhật sản xuất" ở cuối tệp); nhánh v1 tái
  tạo cấu hình API cũ (0,5%/đêm) một cách tường minh.

**English summary.**
- Pre-registered `sim30-v1` (FreshMesh as the old API ran it: *Cân bằng*, `horizon_days = 1`, 0.5%/night
  holding) **fails §1.4 #3 on all three chains**: more waste than the 7-day-mean baseline (+4.2 / +7.1 /
  +8.9 pp) in exchange for far fewer stockouts (−11.2 / −22.2 / −14.6 pp). It sits at a different point of the
  waste–stockout trade-off rather than dominating the baseline; net profit is lower in A (−7.9 [−13.5; −2.2]
  M VND) and C (−94 M VND), and the B interval contains 0 (−6.0 [−12.3; 0.4]).
- Cause (diagnosed on dev seed 999 of the first run only; those diagnostic figures are from the earlier data and
  were not re-measured): the one-day horizon prices the leftover of a *new* 2–3-day lot at the 0.5% holding cost,
  so Cân bằng orders near the 99.5% demand quantile for those SKUs; 1-day SKUs follow the newsvendor ratio
  (0.44–0.53) and stock out ~28%; P50 under-forecast realised demand by ~9% on the dev seed (censored sales fed
  back as history, promo-blind future, no refit). The horizon-L arm does not fix it (waste still +5.7 to +6.9 pp).
- Revision `sim30-v2` (written before any confirmatory run; parameter picked on the dev seed by maximum total
  profit; not re-tuned for this run): overnight carry-over risk cost 20% of unit cost for fresh SKUs. On the 5
  confirmatory seeds it **passes on all three chains** (waste −3.3 / −4.6 / −3.3 pp, stockout −5.1 / −13.1 /
  −4.4 pp, profit +40 / +30 / +60 M VND per 30 days; all 95% intervals exclude 0). It is a post-hoc revision;
  it is now the production default (`fresh_carry_cost_rate_per_day = 0.20`).
- Exploratory: *Tiết kiệm* also cuts waste everywhere but raises stockouts by +7.7 pp in CHAIN_C and by
  +1.3 [0.5; 2.2] pp in CHAIN_A (upper bound above +2.0, so it would fail both); the order-up-to baseline
  (`mean7_net`) wastes least in A and B but loses 35–53% of demand.

**Giới hạn / limitations.** Vị trí, thời tiết và ngày lễ là dữ liệu thật, nhưng doanh số/nhu cầu vẫn do chương trình
sinh, cùng bộ sinh với dữ liệu huấn luyện (chỉ đổi seed nhiễu); mô hình không huấn luyện lại; lead time 0; không có
ràng buộc ngân sách/kho lạnh; không mô phỏng giảm giá cận hạn hay điều chuyển (sẽ giảm thêm hàng bỏ); baseline bỏ
qua tồn kho đúng như mô tả trong spec nên hết hàng 17–30%.

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
