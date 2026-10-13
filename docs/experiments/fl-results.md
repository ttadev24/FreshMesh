# Học liên kết (FL) — kết quả thí nghiệm / Federated learning — experiment results

> **Dữ liệu giả lập (SIMULATED).** Ba chuỗi `CHAIN_A`, `CHAIN_B`, `CHAIN_C` sinh bởi `data_sim` (seed 42).
> Tái lập / reproduce: `scripts/run_fl_experiments.sh` — một tiến trình, BLAS 1 luồng, ≈ 62 phút trên 1 nhân
> CPU (tinh chỉnh 12 cấu hình ≈ 2/3 thời gian), tất định theo seed. Mọi số dưới đây lấy từ **một lần chạy duy
> nhất**: `fl_tuning.csv`, `fl_comparison.csv`, `fl_dp_curve.csv`; biểu đồ `fl_comparison_wape.svg`,
> `fl_dp_curve.svg`.

## 1. Tóm tắt (Tiếng Việt)

- **Cửa hàng mới (cold-start, 14 ngày lịch sử): mô hình FL triển khai tốt hơn Local** — WAPE 0,4596 so với
  0,4707 (tốt hơn **2,4%**), pinball 2,615 so với 2,645 (tốt hơn **1,1%**); đúng ở cả hai chuỗi có cửa hàng mới
  (A: 0,4442 → 0,4346; C: 0,4846 → 0,4726).
- **Nhưng phần lợi này không đến từ việc liên kết.** Ablation "cùng công thức huấn luyện FL nhưng chỉ một chuỗi"
  còn tốt hơn ở cửa hàng mới (WAPE 0,4576, pinball 2,591). Trên tập kiểm tra, việc liên kết tự nó làm cửa hàng
  mới **kém đi nhẹ** (WAPE +0,4%, pinball +0,9% so với ablation); lợi thế so với Local đến từ lịch huấn luyện
  (lr nhỏ hơn, nhiều epoch hơn, fine-tune đầu ra). Trên cửa sổ kiểm định thì ngược lại (liên kết giúp rõ, mục 6)
  — kết quả **không ổn định** giữa hai cửa sổ, với chỉ 2 cửa hàng mới.
- **Trên toàn bộ cửa hàng: FL không tốt hơn Local** — WAPE 0,4360 so với 0,4352 (kém 0,2%), pinball 1,7548 so
  với 1,7504 (kém 0,3%). Nguyên nhân chính là **chuỗi B** (khách văn phòng, khác biệt nhất): WAPE 0,4446 →
  0,4516 (kém 1,6%).
- **Kết luận theo tiêu chí §1.4** ("FL tốt hơn Local-only về WAPE và pinball, rõ nhất ở cửa hàng mới"):
  **đạt một phần** — mô hình FL tốt hơn Local ở cửa hàng mới; **không đạt** ở tổng thể; và trên tập kiểm tra
  phần lợi ở cửa hàng mới không quy được cho liên kết. Chúng tôi báo cáo trung thực, không chọn lọc.
- **Centralized** (gộp dữ liệu) ≈ Local ở tổng thể (0,4350), **kém nhất ở cửa hàng mới** (0,4734).
- **DP mức chuỗi:** với chỉ 3 client, ε ≤ 3 làm hỏng mô hình; ε = 10 → WAPE 0,538; ε = 30 → 0,461;
  ε = 1000 → 0,444 (không DP: 0,436). Mô hình FL đang triển khai **không bật DP**.

## 2. Summary (English)

- **New (cold-start) stores: the deployed FL model beats Local** — WAPE 0.4596 vs 0.4707 (**−2.4%**), pinball
  2.615 vs 2.645 (**−1.1%**), in both chains that have a new store (A 0.4442 → 0.4346, C 0.4846 → 0.4726).
- **That gain is not attributable to federation on the test window.** The single-chain ablation with the same
  training recipe is even better on new stores (WAPE 0.4576, pinball 2.591); federation itself makes new stores
  slightly worse there (+0.4% WAPE, +0.9% pinball vs the ablation). The gain over Local comes from the recipe
  (lower lr, more epochs, head fine-tune). On the validation window federation helped clearly (section 6), so
  the federation effect on cold-start stores is **not stable** across windows, with only 2 new stores.
- **All stores: FL does not beat Local** — WAPE 0.4360 vs 0.4352 (+0.2%), pinball 1.7548 vs 1.7504 (+0.3%),
  driven by **CHAIN_B** (office customers, the most different chain): 0.4446 → 0.4516 (+1.6%).
- **Spec §1.4 is met only partly**: better than Local on new stores, not overall, and on the test window the
  new-store gain is not due to federation.
- **Centralized** ≈ Local overall (0.4350) and worst on new stores (0.4734).
- **DP**: with 3 clients, ε ≤ 3 destroys the model; ε = 10 → 0.538, ε = 30 → 0.461, ε = 1000 → 0.444
  (no DP 0.436). The deployed FL models use **no DP**.

## 3. Thiết lập / Setup

| | |
|---|---|
| Client | Mỗi chuỗi = một Flower `ClientApp`. Dữ liệu thô không rời chuỗi; chỉ gửi trọng số phần thân. |
| Chia sẻ (FedAvg) | Thân mô hình `[E_sku, W1, b1, W2, b2]` (embedding SKU dùng chung — danh mục 30 SKU giống nhau ở cả 3 chuỗi, băm `crc32` vào 256 hàng), trung bình có trọng số theo số mẫu (cả 3 chuỗi đều chạm trần 200 000 dòng nên trọng số bằng nhau). |
| Giữ tại chuỗi (FedPer / kiểu FedBN) | Đầu ra `[Wout, bout]` (huấn luyện cục bộ mỗi vòng, lưu trong `context.state`, cuối cùng fine-tune 2 epoch với thân cố định), `feature_mean/std` (chuẩn hoá cục bộ, không lấy trung bình), hệ số scale từng dòng, offset conformal (CQR trên 28 ngày hiệu chỉnh của chính chuỗi). |
| Mô hình | `QuantileMLP` (64, 32), emb 4 — giống mô hình cục bộ; pinball loss P10/P50/P90. |
| Tối ưu | Adam cục bộ, lr giảm theo cosine qua các vòng, weight decay 1e-3, batch 1024, đúng các dòng huấn luyện mà `train_local` dùng với cùng seed (tối đa 200 000 / chuỗi). |
| Cấu hình chọn | **40 vòng × 2 epoch cục bộ, lr 5e-4**, fine-tune đầu ra 2 epoch (lr 1e-3) — là giá trị mặc định của `FLConfig`. |
| Flower | `flwr` 1.39: `flwr.serverapp.strategy.FedAvg` (+ `DifferentialPrivacyClientSideFixedClipping`), `flwr.clientapp.ClientApp` (+ `fixedclipping_mod`), truyền tin qua `InProcessGrid`. |

**Chế độ Flower — nói rõ / Flower mode, stated plainly:** simulation engine của Flower (`run_simulation`) chỉ
có backend Ray (`flwr/server/superlink/fleet/vce/backend/` chỉ có `raybackend.py`), mà Ray không được cài và
không được sửa `pyproject.toml`. Triển khai SuperLink/SuperNode qua gRPC cần một tiến trình chạy lâu cho mỗi
chuỗi cùng một gói FAB; demo không khởi động chúng. Vì vậy chúng tôi chạy **đúng mã chiến lược (ServerApp
strategy) và ClientApp của Flower** qua một cài đặt giao diện `Grid` trong cùng tiến trình (`InProcessGrid`:
deep-copy nội dung ở ranh giới, một `Context` cho mỗi node). Cách này dựa vào hai chi tiết nội bộ của Flower:
đặt `flwr.supercore.task_identity.TaskIdentity` (như `flwr.server.compat.app`) và gán
`metadata._message_id` (như `InMemoryGrid`). Đây **không** phải gRPC và **không** phải simulation engine. Câu
trả lời được sắp theo node để phép cộng dấu phẩy động tất định (Flower lấy mẫu node bằng `random.sample`).

## 4. Giao thức đánh giá cố định / Fixed evaluation protocol

1. **Chọn siêu tham số chỉ cho FL, trên cửa sổ kiểm định**: 28 ngày cuối của giai đoạn huấn luyện của phép chia
   kiểm tra (hiệu chỉnh trên 28 ngày trước đó, huấn luyện trên phần còn lại) — không đọc ngày nào của cửa sổ
   hiệu chỉnh/kiểm tra thật. Trong cửa sổ này cửa hàng đã hoạt động đầu tiên của mỗi chuỗi (A-CH1, B-CH1, C-CH1)
   được **giả lập thành cửa hàng mới** (chỉ còn 14 ngày lịch sử). Điểm = trung bình theo chuỗi của
   pinball / nhu cầu trung bình, lấy trung bình đều giữa "tất cả cửa hàng" và "cửa hàng mới giả lập".
   Lưới: vòng {20, 40} × epoch cục bộ {1, 2} × lr {5e-4, 1e-3, 2e-3}, fine-tune đầu ra 2 epoch, seed 0.
2. **So sánh trên cửa sổ kiểm tra giữ lại** của `forecasting.service` (2026-09-03 → 2026-09-30), seed 0, 1, 2.
   Mọi phương pháp dùng cùng dòng, cùng đặc trưng, cùng hiệu chỉnh conformal theo chuỗi và cùng mã đo
   (`client.eval_sums`, đã kiểm thử khớp `service._evaluate`). "ALL" = gộp mọi dòng kiểm tra của 3 chuỗi
   (WAPE = Σ|sai số| / Σ nhu cầu; pinball, độ phủ = trung bình theo dòng).
3. **Công bằng:** cấu hình của Local (`TrainConfig` mặc định) đã được agent trước tinh chỉnh **trên chính cửa sổ
   kiểm tra**; FL thì không — nghiêng về phía Local.
4. **Ablation `local_fl_trainer`**: đúng pipeline FL nhưng chỉ 1 client (không liên kết), cùng cấu hình — tách
   hiệu ứng liên kết khỏi hiệu ứng công thức huấn luyện.
5. **Công khai lịch sử:** lần chạy đầu dùng lưới không có lr (lr cố định 2e-3, chọn 40 × 1). Sau đó, chỉ trên
   cửa sổ kiểm định, lr 1e-3 cho điểm tốt hơn (0,14329 so với 0,14375), nên lr được đưa vào lưới và **toàn bộ**
   thí nghiệm chạy lại; số của lần đầu bị thay thế. Người thực hiện đã thấy kết quả kiểm tra của lần đầu
   (FL cửa hàng mới 0,4641, tổng thể 0,4361 — cùng xu hướng) trước khi mở rộng lưới.
6. **Độ bất định:** "±" là độ lệch chuẩn qua 3 seed, chỉ đo ngẫu nhiên của huấn luyện — **không** phải độ bất
   định theo cửa hàng hay theo ngày. Kết luận về cửa hàng mới dựa trên 2 cửa hàng × 14 ngày (4 200 dòng).

## 5. Kết quả trên tập kiểm tra / Held-out results (mean ± std over 3 seeds)

Tất cả chuỗi gộp / all chains pooled:

| Phương pháp / Method | WAPE (tất cả) | Pinball (tất cả) | Độ phủ P10–P90 | WAPE cửa hàng mới | Pinball cửa hàng mới |
|---|---|---|---|---|---|
| Local (`train_local`) | **0.4352** ± 0.0001 | **1.7504** ± 0.0007 | 0.795 | 0.4707 ± 0.0006 | 2.6447 ± 0.0059 |
| **FL (FedAvg + FedPer)** | 0.4360 ± 0.0001 | 1.7548 ± 0.0006 | 0.795 | 0.4596 ± 0.0018 | 2.6154 ± 0.0065 |
| Local, FL trainer (ablation) | 0.4363 ± 0.0005 | 1.7549 ± 0.0025 | 0.793 | **0.4576** ± 0.0004 | **2.5908** ± 0.0076 |
| Centralized (gộp dữ liệu) | 0.4350 ± 0.0002 | 1.7516 ± 0.0004 | 0.795 | 0.4734 ± 0.0012 | 2.6783 ± 0.0032 |

FL so với Local, `(local − fl) / local` (dương = FL tốt hơn): WAPE **−0.17%**, pinball **−0.25%**,
WAPE cửa hàng mới **+2.38%**, pinball cửa hàng mới **+1.11%** (các giá trị này là `improvement_vs_local` mà
`fl_summary` trả về). FL so với ablation (hiệu ứng riêng của liên kết): WAPE tổng thể +0.07%, cửa hàng mới
−0.44%, pinball cửa hàng mới −0.95%.

Theo chuỗi / per chain (WAPE; pinball trong ngoặc), mean of 3 seeds:

| Chuỗi | Nhóm | Local | FL | Local, FL trainer | Centralized |
|---|---|---|---|---|---|
| CHAIN_A | tất cả | 0.3777 (1.381) | 0.3768 (1.378) | 0.3799 (1.389) | **0.3766** (1.376) |
| CHAIN_A | cửa hàng mới A-CH6 | 0.4442 (1.696) | 0.4346 (1.671) | **0.4285** (1.659) | 0.4447 (1.711) |
| CHAIN_B | tất cả (không có cửa hàng mới) | **0.4446** (1.054) | 0.4516 (1.068) | 0.4468 (1.056) | 0.4457 (1.056) |
| CHAIN_C | tất cả | 0.4637 (2.609) | **0.4633** (2.613) | 0.4637 (2.613) | 0.4634 (2.615) |
| CHAIN_C | cửa hàng mới C-CH7 | 0.4846 (3.594) | **0.4726** (3.560) | 0.4729 (3.522) | 0.4884 (3.646) |

Độ phủ P10–P90 sau hiệu chỉnh conformal của từng chuỗi: 0,778–0,801 cho mọi phương pháp và nhóm (mục tiêu 0,80).

## 6. Phân tích và điều tra / Analysis and investigation

- **Kiểm định và kiểm tra cho tín hiệu khác nhau về liên kết ở cửa hàng mới.** Trên cửa sổ kiểm định, FL tốt
  hơn ablation một chuỗi ở cửa hàng mới giả lập (pinball chuẩn hoá) ở 11/12 cấu hình; với cấu hình được chọn
  WAPE 0,4596 so với 0,4887. Trên tập kiểm tra, ablation lại tốt hơn FL ở cửa hàng mới. Giải thích khả dĩ (chưa
  kiểm chứng): cửa hàng mới thật (A-CH6 dân cư, C-CH7 gần chợ) giống các cửa hàng cùng chuỗi hơn cửa hàng giả
  lập; và chọn cấu hình theo điểm FL có thể đã chọn đúng điểm mà ablation yếu trên kiểm định (ablation ở cấu
  hình này kém nhất lưới: 0,1476). Với 2 cửa hàng, không đủ để kết luận.
  *Validation and test disagree on the federation effect for cold-start stores; with 2 stores we cannot settle it.*
- **Chuỗi B bị thiệt** ở mọi lần chạy: B có tệp khách văn phòng, vắng cuối tuần — khác hẳn A và C; thân chung
  bị kéo về A/C. Trên cửa sổ kiểm định (kiểm tra theo chuỗi với cấu hình của lần chạy đầu), cửa hàng mới giả lập của B cũng kém hơn khi dùng FL (WAPE 0,530 so với 0,510). Đây là hiện tượng
  non-IID thật, không phải lỗi cài đặt. *CHAIN_B is consistently hurt by the shared body (non-IID).*
- **Đã thử, chỉ trên cửa sổ kiểm định** (cấu hình chọn của lần chạy đầu, điểm 0,14375; khoảng chênh giữa các
  cấu hình ≈ 0,0005):
  - vòng / epoch cục bộ / fine-tune đầu ra (lưới) — khác biệt rất nhỏ;
  - lr 1e-3: 0,14329 (tốt hơn → đưa lr vào lưới, chạy lại toàn bộ); lr 5e-3: 0,14423 (kém);
  - fine-tune **toàn bộ** mạng sau FL (2 hoặc 4 epoch) thay vì chỉ đầu ra: 0,14417 / 0,14445 (kém), B gần như
    không đổi → giữ FedPer chỉ cá nhân hoá đầu ra;
  - khởi động đầu ra (head warm start: 2 epoch cục bộ trước vòng 1, giữ đầu ra): 0,14409 (kém) → bỏ.
  Không tinh chỉnh gì trên cửa sổ kiểm tra. *Tried on validation only; none beyond the lr change helped.*
- **Hướng tiếp theo (chưa làm):** cá nhân hoá thêm lớp ẩn cuối (FedPer 2 lớp), phân cụm client (để B học
  riêng), hoặc để mỗi chuỗi chọn Local hay FL theo điểm kiểm định của chính nó; thêm nhiều chuỗi / cửa hàng mới
  để đo hiệu ứng cold-start chắc chắn hơn.
- **Centralized có lẽ không phải cận trên ở đây** (giả thuyết, chưa kiểm chứng riêng): nó dùng chuẩn hoá gộp và
  một đầu ra chung cho ba chuỗi non-IID; kết quả gần Local ở tổng thể và kém ở cửa hàng mới.

## 7. Đường cong ε – WAPE / epsilon vs WAPE (`fl_dp_curve.csv`, `fl_dp_curve.svg`)

DP mức chuỗi (client-level) trên phần thân được gửi đi: mỗi chuỗi cắt chuẩn L2 của bản cập nhật thân về
`C = 0.3459` (trung vị chuẩn cập nhật của cấu hình được chọn, chạy không DP trên cửa sổ kiểm định — bản thân
lựa chọn này dùng dữ liệu riêng và **không** được tính vào ε); máy chủ lấy trung bình **đều** 3 bản cập nhật đã
cắt và cộng nhiễu Gaussian `N(0, (z·C/3)²)` (Flower `fixedclipping_mod` + `DifferentialPrivacyClientSideFixedClipping`).
Kế toán (`forecasting/fl/dp.py`): zCDP của cơ chế Gaussian, `ρ = R / (2z²)` sau `R = 40` vòng,
`ε = ρ + 2√(ρ ln(1/δ))`, `δ = 1e-5`; mọi chuỗi tham gia mọi vòng nên **không có khuếch đại do lấy mẫu**. Đây là
chặn chuyển đổi chuẩn (hơi lỏng), không phải bộ kế toán RDP/PLD số chặt nhất (gói `dp-accounting` mà
`RdpAccountant` của Flower cần không được cài). Bảo đảm chỉ áp dụng cho phần thân gửi đi; đầu ra cá nhân và
offset conformal không rời chuỗi; chỉ số đánh giá là thống kê gộp, nằm ngoài bảo đảm này. Khi bật DP, FedAvg
dùng trọng số đều (trên dữ liệu này giống hệt trọng số theo mẫu).

| ε (δ = 1e-5) | hệ số nhiễu z | WAPE tất cả: mean (3 seed) | WAPE từng seed | Pinball mean | WAPE cửa hàng mới mean |
|---|---|---|---|---|---|
| 1 | 30.99 | 123.9 | 146.8 / 80.4 / 144.6 | 499.8 | 206.1 |
| 3 | 10.74 | 3.711 | 6.68 / 1.80 / 2.66 | 13.12 | 5.290 |
| 10 | 3.59 | 0.5382 | 0.605 / 0.521 / 0.489 | 2.122 | 0.6082 |
| 30 | 1.47 | 0.4608 | 0.456 / 0.461 / 0.466 | 1.865 | 0.4984 |
| 100 | 0.62 | 0.4538 | 0.453 / 0.453 / 0.455 | 1.838 | 0.4879 |
| 1000 | 0.157 | 0.4437 | 0.446 / 0.440 / 0.445 | 1.788 | 0.4785 |
| không DP / none | — | 0.4360 | 0.436 / 0.436 / 0.436 | 1.755 | 0.4596 |

(Local: 0,4352; cửa hàng mới 0,4707.) Với ε ≤ 3 trung bình bị chi phối bởi seed xấu nhất (xem cột từng seed).
Với 3 client, nhiễu trên trung bình chỉ chia cho 3 nên DP rất tốn: không mức ε nào thử ở đây vừa có bảo đảm
mạnh vừa bằng Local. Cần nhiều chuỗi hơn (nhiễu trên trung bình giảm theo 1/n) hoặc ít vòng hơn khi bật DP.
*With 3 clients DP is expensive; no tested ε gives both a strong guarantee and Local-level accuracy.*

## 8. Sử dụng / Usage

- `uv run python -m forecasting.fl train [--rounds 40] [--dp-epsilon E] [--clip-norm 0.3459] [--seed 0]` → ghi
  `data/models/<chuỗi>.fl.npz/.json` (thân chung + đầu ra riêng + chuẩn hoá riêng + offset conformal riêng).
  Mô hình triển khai (seed 0, không DP) khớp đúng dòng `fl, seed 0` trong `fl_comparison.csv`.
- `forecast_demand(..., model="fl")` hoặc biến môi trường `FRESHMESH_FORECAST_MODEL=fl` để dùng mô hình FL
  (mặc định vẫn là `local`).
- `forecasting.fl.fl_summary(data_dir, docs_dir)` → dữ liệu cho `GET /api/network/fl` (đọc từ các CSV ở đây;
  báo lỗi rõ nếu chưa chạy thí nghiệm).
