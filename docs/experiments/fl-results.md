# Học liên kết (FL) — kết quả thí nghiệm / Federated learning — experiment results

> **Nguồn dữ liệu.** Ba chuỗi `CHAIN_A`, `CHAIN_B`, `CHAIN_C` dựng bởi `data_sim` (seed 42). Vị trí cửa hàng thật
> từ OpenStreetMap (ODbL), gán chuỗi bằng chương trình. Lượng mưa TP.HCM lấy từ Open-Meteo (CC BY 4.0). Ngày lễ
> Việt Nam theo văn bản pháp luật và âm lịch. **Nhu cầu bán hàng vẫn do chương trình sinh** (tham số giả định).
> Tái lập / reproduce: `scripts/run_fl_experiments.sh` (`forecasting.fl experiment` rồi `forecasting.fl train`).
> Script chạy một tiến trình, BLAS 1 luồng; **chạy một lõi ≈ 1 giờ** (lần chạy này: 15:04 → 16:02, thí nghiệm
> 3 318 giây, huấn luyện mô hình triển khai 151 giây), tất định theo seed. Mọi số dưới đây lấy từ **một lần chạy
> duy nhất** trên dữ liệu dựng lại: `fl_tuning.csv`, `fl_comparison.csv`, `fl_dp_curve.csv`; biểu đồ
> `fl_comparison_wape.svg`, `fl_dp_curve.svg`.

## 1. Tóm tắt (Tiếng Việt)

- **Trên toàn bộ cửa hàng: FL kém Local.** WAPE 0,4432 so với 0,4408 (kém 0,54%), pinball 1,7540 so với 1,7426
  (kém 0,66%). FL kém Local ở cả ba chuỗi: A kém 0,44%, B kém 0,88%, C kém 0,47% WAPE.
- **Cửa hàng mới (cold-start, 14 ngày lịch sử): FL cũng không tốt hơn Local.** WAPE 0,4775 so với 0,4761 (kém
  0,29%), pinball 2,1709 so với 2,1645 (kém 0,30%). A-CH6: 0,4360 → 0,4390 (kém hơn); C-CH7: 0,4977 → 0,4982
  (ngang nhau). Chênh lệch nhỏ hơn độ lệch chuẩn qua seed của Local (0,0027), tức là **trong mức nhiễu**.
- **Liên kết có giúp cửa hàng mới so với cùng công thức huấn luyện một chuỗi.** So với ablation (cùng pipeline FL
  nhưng chỉ một chuỗi), FL tốt hơn ở cửa hàng mới: WAPE 0,4775 so với 0,4808 (tốt hơn 0,68%), pinball tốt hơn
  0,99%. Ablation là phương pháp **kém nhất** ở cửa hàng mới. Nhưng hiệu ứng này không vững: ở seed 0 ablation
  lại tốt hơn FL (0,4720 so với 0,4746), và độ lệch chuẩn của ablation là 0,0064. Công thức huấn luyện FL kém
  công thức của Local (được tinh chỉnh trên chính tập kiểm tra), nên phần lợi do liên kết không đủ bù.
- **Chuỗi B** (khách văn phòng, vắng cuối tuần, khác biệt nhất) chịu thiệt nhiều nhất: WAPE 0,4542 → 0,4582
  (kém 0,88%). Ablation một chuỗi trên B gần bằng Local (0,4537), nên phần thiệt ở B **do việc liên kết** (FL kém
  ablation 0,98%). B không còn là nguyên nhân duy nhất: A và C cũng kém nhẹ.
- **Kết luận theo tiêu chí §1.4** ("FL tốt hơn Local-only về WAPE và pinball, rõ nhất ở cửa hàng mới"):
  **không đạt**. FL không tốt hơn Local ở tổng thể, cũng không tốt hơn ở cửa hàng mới. Chúng tôi báo cáo trung
  thực, không chọn lọc. (Trên dữ liệu cũ, kết luận là "đạt một phần"; lần chạy lại này không giữ được kết quả đó.)
- **Centralized** (gộp dữ liệu) ≈ Local ở tổng thể (0,4411); ở cửa hàng mới 0,4788, kém Local và FL nhưng tốt hơn
  ablation.
- **DP mức chuỗi:** với chỉ 3 client, ε ≤ 3 làm hỏng mô hình. Các mức còn lại: ε = 10 → WAPE 0,529; ε = 30 → 0,466;
  ε = 100 → 0,460; ε = 1000 → 0,448 (không DP: 0,443). Không mức nào bằng Local. Mô hình FL triển khai **không bật
  DP**.
- **Mô hình triển khai** (`data/models/*.fl.*`, seed 0, không DP) dùng đúng cấu hình đã chọn (40 vòng × 1 epoch,
  lr 1e-3) và tái lập đúng các dòng `fl, seed 0` trong `fl_comparison.csv` (mục 8).

## 2. Summary (English)

- **All stores: FL is worse than Local.** WAPE 0.4432 vs 0.4408 (−0.54%), pinball 1.7540 vs 1.7426 (−0.66%).
  It is worse in every chain: A −0.44%, B −0.88%, C −0.47% WAPE.
- **New (cold-start) stores: FL does not beat Local either.** WAPE 0.4775 vs 0.4761 (−0.29%), pinball 2.1709 vs
  2.1645 (−0.30%). A-CH6 gets worse (0.4360 → 0.4390) and C-CH7 is a tie (0.4977 vs 0.4982). The gaps are smaller
  than Local's seed std (0.0027), so they are within noise.
- **Federation does help new stores relative to the same recipe on a single chain.** Against the single-chain
  ablation, FL is better on new stores: WAPE 0.4775 vs 0.4808 (+0.68%), pinball +0.99%. The ablation is the
  worst method on new stores. This effect is not robust: the ablation wins on seed 0 (0.4720 vs 0.4746) and its
  std is 0.0064. The FL training recipe trails Local's recipe, which was tuned on the test window, and federation
  does not make up the difference.
- **CHAIN_B** (office customers, the most different chain) loses most: 0.4542 → 0.4582 (−0.88%). The single-chain
  ablation on B is about equal to Local (0.4537), so B's loss is due to federation (FL is 0.98% worse than the
  ablation). B is no longer the only chain that loses; A and C are slightly worse too.
- **Spec §1.4 is not met**: FL is not better than Local overall or on new stores. On the old data the verdict was
  "partly met"; that result did not hold up on the rebuilt data.
- **Centralized** ≈ Local overall (0.4411); on new stores it scores 0.4788, worse than Local and FL but better than
  the ablation.
- **DP**: with 3 clients, ε ≤ 3 destroys the model. The other levels: ε = 10 → 0.529, ε = 30 → 0.466,
  ε = 100 → 0.460, ε = 1000 → 0.448 (no DP 0.443). None reaches Local. The deployed FL models use **no DP**.
- **Deployed models** (`data/models/*.fl.*`, seed 0, no DP) use the selected configuration (40 rounds × 1 epoch,
  lr 1e-3) and reproduce the `fl, seed 0` rows of `fl_comparison.csv` (section 8).

## 3. Thiết lập / Setup

| | |
|---|---|
| Client | Mỗi chuỗi = một Flower `ClientApp`. Dữ liệu thô không rời chuỗi; chỉ gửi trọng số phần thân. |
| Chia sẻ (FedAvg) | Thân mô hình `[E_sku, W1, b1, W2, b2]`. Embedding SKU dùng chung, vì danh mục 30 SKU giống nhau ở cả 3 chuỗi (băm `crc32` vào 256 hàng). Lấy trung bình có trọng số theo số mẫu; cả 3 chuỗi đều chạm trần 200 000 dòng nên trọng số bằng nhau. |
| Giữ tại chuỗi (FedPer / kiểu FedBN) | Đầu ra `[Wout, bout]`: huấn luyện cục bộ mỗi vòng, lưu trong `context.state`, cuối cùng fine-tune 2 epoch với thân cố định. Ngoài ra còn `feature_mean/std` (chuẩn hoá cục bộ, không lấy trung bình), hệ số scale từng dòng và offset conformal (CQR trên 28 ngày hiệu chỉnh của chính chuỗi). |
| Mô hình | `QuantileMLP` (64, 32), emb 4 — giống mô hình cục bộ; pinball loss P10/P50/P90. |
| Tối ưu | Adam cục bộ, lr giảm theo cosine qua các vòng, weight decay 1e-3, batch 1024. Dùng đúng các dòng huấn luyện mà `train_local` dùng, cùng seed (tối đa 200 000 / chuỗi). |
| Cấu hình chọn (lần chạy này) | **40 vòng × 1 epoch cục bộ, lr 1e-3**, fine-tune đầu ra 2 epoch (lr 1e-3). Trung vị chuẩn cập nhật thân là 0,3554. Đây là giá trị mặc định của `FLConfig` (`rounds=40`, `local_epochs=1`, `lr=1e-3`, `clip_norm=0.3554`). |
| Flower | `flwr` 1.39: `flwr.serverapp.strategy.FedAvg` (+ `DifferentialPrivacyClientSideFixedClipping`), `flwr.clientapp.ClientApp` (+ `fixedclipping_mod`), truyền tin qua `InProcessGrid`. |

**Chế độ Flower — nói rõ / Flower mode, stated plainly:** simulation engine của Flower (`run_simulation`) chỉ có
backend Ray (`flwr/server/superlink/fleet/vce/backend/` chỉ có `raybackend.py`). Ray không được cài, và không được
sửa `pyproject.toml`. Triển khai SuperLink/SuperNode qua gRPC cần một tiến trình chạy lâu cho mỗi chuỗi cùng một
gói FAB; demo không khởi động chúng. Vì vậy chúng tôi chạy **đúng mã chiến lược (ServerApp strategy) và ClientApp
của Flower** qua một cài đặt giao diện `Grid` trong cùng tiến trình (`InProcessGrid`: deep-copy nội dung ở ranh
giới, một `Context` cho mỗi node). Cách này dựa vào hai chi tiết nội bộ của Flower: đặt
`flwr.supercore.task_identity.TaskIdentity` (như `flwr.server.compat.app`) và gán `metadata._message_id` (như
`InMemoryGrid`). Đây **không** phải gRPC và **không** phải simulation engine. Flower lấy mẫu node bằng
`random.sample`, nên câu trả lời được sắp theo node để phép cộng dấu phẩy động tất định.

## 4. Giao thức đánh giá cố định / Fixed evaluation protocol

1. **Chọn siêu tham số chỉ cho FL, trên cửa sổ kiểm định.** Cửa sổ này là 28 ngày cuối của giai đoạn huấn luyện
   của phép chia kiểm tra; hiệu chỉnh trên 28 ngày trước đó, huấn luyện trên phần còn lại. Không đọc ngày nào của
   cửa sổ hiệu chỉnh/kiểm tra thật. Trong cửa sổ này, cửa hàng đã hoạt động đầu tiên của mỗi chuỗi (A-CH1, B-CH1,
   C-CH1) được **giả lập thành cửa hàng mới**, chỉ còn 14 ngày lịch sử. Điểm = trung bình theo chuỗi của
   pinball / nhu cầu trung bình, lấy trung bình đều giữa "tất cả cửa hàng" và "cửa hàng mới giả lập".
   Lưới: vòng {20, 40} × epoch cục bộ {1, 2} × lr {5e-4, 1e-3, 2e-3}, fine-tune đầu ra 2 epoch, seed 0.
   Lưới và mã giống hệt lần chạy trên dữ liệu cũ; không điều chỉnh gì sau khi thấy kết quả của lần chạy này.
2. **So sánh trên cửa sổ kiểm tra giữ lại** của `forecasting.service` (2026-09-03 → 2026-09-30), seed 0, 1, 2.
   Mọi phương pháp dùng cùng dòng, cùng đặc trưng, cùng hiệu chỉnh conformal theo chuỗi và cùng mã đo
   (`client.eval_sums`, đã kiểm thử khớp `service._evaluate`). "ALL" = gộp mọi dòng kiểm tra của 3 chuỗi
   (WAPE = Σ|sai số| / Σ nhu cầu; pinball và độ phủ = trung bình theo dòng).
3. **Công bằng:** cấu hình của Local (`TrainConfig` mặc định) đã được agent trước tinh chỉnh **trên chính cửa sổ
   kiểm tra**; FL thì không. Điều này nghiêng về phía Local.
4. **Ablation `local_fl_trainer`**: đúng pipeline FL nhưng chỉ 1 client (không liên kết), cùng cấu hình. Ablation
   tách hiệu ứng liên kết khỏi hiệu ứng công thức huấn luyện.
5. **Công khai lịch sử (dữ liệu cũ, trước khi dựng lại dữ liệu):** lần chạy đầu dùng lưới không có lr (lr cố định
   2e-3, chọn 40 × 1). Sau đó, chỉ trên cửa sổ kiểm định, lr 1e-3 cho điểm tốt hơn (0,14329 so với 0,14375). Vì
   vậy lr được đưa vào lưới và **toàn bộ** thí nghiệm được chạy lại. Người thực hiện đã thấy kết quả kiểm tra của
   lần đầu trước khi mở rộng lưới. Lưới đó được dùng nguyên vẹn cho lần chạy trên dữ liệu dựng lại này.
6. **Độ bất định:** "±" là độ lệch chuẩn quần thể (ddof = 0) qua 3 seed. Nó chỉ đo ngẫu nhiên của huấn luyện,
   **không** phải độ bất định theo cửa hàng hay theo ngày. Kết luận về cửa hàng mới dựa trên 2 cửa hàng × 14 ngày
   (4 200 dòng).

## 5. Kết quả trên tập kiểm tra / Held-out results (mean ± std over 3 seeds)

Tất cả chuỗi gộp / all chains pooled:

| Phương pháp / Method | WAPE (tất cả) | Pinball (tất cả) | Độ phủ P10–P90 | WAPE cửa hàng mới | Pinball cửa hàng mới |
|---|---|---|---|---|---|
| **Local (`train_local`)** | **0.4408** ± 0.0003 | **1.7426** ± 0.0015 | 0.799 | **0.4761** ± 0.0027 | **2.1645** ± 0.0158 |
| FL (FedAvg + FedPer) | 0.4432 ± 0.0002 | 1.7540 ± 0.0009 | 0.797 | 0.4775 ± 0.0022 | 2.1709 ± 0.0149 |
| Local, FL trainer (ablation) | 0.4414 ± 0.0004 | 1.7464 ± 0.0009 | 0.797 | 0.4808 ± 0.0064 | 2.1927 ± 0.0414 |
| Centralized (gộp dữ liệu) | 0.4411 ± 0.0003 | 1.7453 ± 0.0012 | 0.800 | 0.4788 ± 0.0021 | 2.1739 ± 0.0074 |

FL so với Local, `(local − fl) / local` (dương = FL tốt hơn): WAPE **−0.54%**, pinball **−0.66%**,
WAPE cửa hàng mới **−0.29%**, pinball cửa hàng mới **−0.30%**. Đây là các giá trị `improvement_vs_local` mà
`fl_summary` trả về (−0.0054, −0.0066, −0.0029, −0.0030).

FL so với ablation, `(ablation − fl) / ablation` (hiệu ứng riêng của liên kết; dương = liên kết giúp): WAPE tổng
thể −0.40%, pinball tổng thể −0.44%; WAPE cửa hàng mới **+0.68%**, pinball cửa hàng mới **+0.99%**.

WAPE cửa hàng mới theo seed (0 / 1 / 2): Local 0.4747 / 0.4799 / 0.4737; FL 0.4746 / 0.4798 / 0.4781; ablation
0.4720 / 0.4831 / 0.4872. FL ngang Local ở seed 0 và 1, kém ở seed 2. FL tốt hơn ablation ở seed 1 và 2, kém ở
seed 0.

Theo chuỗi / per chain (WAPE; pinball trong ngoặc), mean of 3 seeds:

| Chuỗi | Nhóm | Local | FL | Local, FL trainer | Centralized |
|---|---|---|---|---|---|
| CHAIN_A | tất cả | 0.3728 (1.454) | 0.3744 (1.461) | 0.3740 (1.459) | **0.3725** (1.454) |
| CHAIN_A | cửa hàng mới A-CH6 (dân cư) | **0.4360** (1.397) | 0.4390 (1.406) | 0.4467 (1.436) | 0.4367 (1.394) |
| CHAIN_B | tất cả (không có cửa hàng mới) | 0.4542 (1.084) | 0.4582 (1.094) | **0.4537** (1.084) | 0.4559 (1.090) |
| CHAIN_C | tất cả | **0.4787** (2.504) | 0.4810 (2.521) | 0.4794 (2.510) | 0.4790 (2.506) |
| CHAIN_C | cửa hàng mới C-CH7 (chợ) | **0.4977** (2.932) | 0.4982 (2.936) | 0.4991 (2.950) | 0.5015 (2.954) |

FL so với Local theo chuỗi (WAPE): A −0.44%, B −0.88%, C −0.47%; cửa hàng mới A −0.69%, C −0.10%.
FL so với ablation (WAPE): A −0.12%, B −0.98%, C −0.33%; cửa hàng mới A +1.72%, C +0.18%.

Độ phủ P10–P90 sau hiệu chỉnh conformal của từng chuỗi (mục tiêu 0,80):
- Nhóm "tất cả" theo chuỗi: 0,786–0,809. Thấp nhất là C (0,786–0,795 tuỳ phương pháp).
- Gộp toàn bộ: 0,797–0,800.
- Cửa hàng mới: **0,740–0,780**, tức là thiếu độ phủ ở mọi phương pháp. Offset conformal được hiệu chỉnh trên cửa
  hàng đã có lịch sử.

## 6. Phân tích và điều tra / Analysis and investigation

- **Kiểm định và kiểm tra cùng chiều về hiệu ứng liên kết ở cửa hàng mới.**
  - Kiểm định (`fl_tuning.csv`): FL có điểm tốt hơn ablation một chuỗi ở 9/12 cấu hình. Ở cửa hàng mới giả lập,
    FL có pinball chuẩn hoá tốt hơn ở 7/12 cấu hình (một trường hợp gần như hoà).
  - Với cấu hình được chọn: WAPE cửa hàng mới giả lập là 0,4395 (FL) so với 0,4473 (ablation); WAPE tổng thể là
    0,4279 so với 0,4329.
  - Kiểm tra: FL cũng tốt hơn ablation ở cửa hàng mới, trung bình +0,68%, nhưng không ở mọi seed.
  - Trên dữ liệu cũ, hai cửa sổ cho tín hiệu ngược nhau; trên dữ liệu dựng lại thì không còn mâu thuẫn đó.
  - Vấn đề nằm ở chỗ khác: công thức FL (dù có liên kết) vẫn kém Local, vì cấu hình của Local được tinh chỉnh trên
    chính tập kiểm tra. Với 2 cửa hàng mới, không đủ để kết luận chắc.

  *Validation and test now agree on the direction of the federation effect for cold-start stores (it helps
  relative to the single-chain ablation), but FL still does not beat Local.*
- **Chuỗi B bị thiệt nhiều nhất.** B có tệp khách văn phòng, vắng cuối tuần, khác hẳn A và C, nên thân chung bị kéo
  về A/C. Trên B, ablation một chuỗi gần bằng Local (+0,10%), còn FL kém ablation 0,98%: phần thiệt này là do liên
  kết. Đây là hiện tượng non-IID thật, không phải lỗi cài đặt. Khác với dữ liệu cũ, A và C cũng kém Local nhẹ
  (−0,44%, −0,47%), nên B không phải nguyên nhân duy nhất.

  *CHAIN_B is hurt most by the shared body (non-IID); A and C are slightly worse too.*
- **Độ nhạy theo cấu hình (kiểm định):** điểm FL trong lưới chỉ dao động 0,13863–0,14055. Cấu hình chọn
  (40 × 1, lr 1e-3) có điểm 0,13863, sát các cấu hình 40 × 1 lr 5e-4 (0,13887) và 40 × 2 lr 5e-4 (0,13896). Lựa
  chọn phụ thuộc vào khác biệt rất nhỏ.
- **Đã thử trên dữ liệu cũ, chỉ trên cửa sổ kiểm định (chưa chạy lại trên dữ liệu dựng lại):**
  - lr 5e-3 kém hơn;
  - fine-tune **toàn bộ** mạng sau FL (2 hoặc 4 epoch) thay vì chỉ đầu ra cũng kém hơn, và B gần như không đổi.
    Vì vậy giữ FedPer chỉ cá nhân hoá đầu ra;
  - khởi động đầu ra (head warm start: 2 epoch cục bộ trước vòng 1) kém hơn, nên bỏ.

  Không tinh chỉnh gì trên cửa sổ kiểm tra.
- **Hướng tiếp theo (chưa làm):**
  - cá nhân hoá thêm lớp ẩn cuối (FedPer 2 lớp);
  - phân cụm client để B học riêng;
  - để mỗi chuỗi chọn Local hay FL theo điểm kiểm định của chính nó;
  - tinh chỉnh Local và FL trên cùng một cửa sổ kiểm định để so sánh công bằng;
  - thêm nhiều chuỗi / cửa hàng mới để đo hiệu ứng cold-start chắc chắn hơn.
- **Centralized có lẽ không phải cận trên ở đây** (giả thuyết, chưa kiểm chứng riêng). Nó dùng chuẩn hoá gộp và một
  đầu ra chung cho ba chuỗi non-IID. Kết quả gần Local ở tổng thể và kém Local ở cửa hàng mới.

## 7. Đường cong ε – WAPE / epsilon vs WAPE (`fl_dp_curve.csv`, `fl_dp_curve.svg`)

**Cơ chế.** DP mức chuỗi (client-level) áp dụng trên phần thân được gửi đi. Mỗi chuỗi cắt chuẩn L2 của bản cập
nhật thân về `C = 0.3554`. Giá trị này là trung vị chuẩn cập nhật của cấu hình được chọn, đo khi chạy không DP trên
cửa sổ kiểm định. Bản thân lựa chọn này dùng dữ liệu riêng và **không** được tính vào ε. Máy chủ lấy trung bình
**đều** 3 bản cập nhật đã cắt và cộng nhiễu Gaussian `N(0, (z·C/3)²)` (Flower `fixedclipping_mod` +
`DifferentialPrivacyClientSideFixedClipping`).

**Kế toán** (`forecasting/fl/dp.py`): zCDP của cơ chế Gaussian, `ρ = R / (2z²)` sau `R = 40` vòng,
`ε = ρ + 2√(ρ ln(1/δ))`, `δ = 1e-5`. Mọi chuỗi tham gia mọi vòng nên **không có khuếch đại do lấy mẫu**. Đây là
chặn chuyển đổi chuẩn (hơi lỏng), không phải bộ kế toán RDP/PLD số chặt nhất: gói `dp-accounting` mà
`RdpAccountant` của Flower cần không được cài.

**Phạm vi bảo đảm.** Bảo đảm chỉ áp dụng cho phần thân gửi đi. Đầu ra cá nhân và offset conformal không rời chuỗi.
Chỉ số đánh giá là thống kê gộp, nằm ngoài bảo đảm này. Khi bật DP, FedAvg dùng trọng số đều; trên dữ liệu này
điều đó giống hệt trọng số theo mẫu.

| ε (δ = 1e-5) | hệ số nhiễu z | WAPE tất cả: mean (3 seed) | WAPE từng seed | Pinball mean | WAPE cửa hàng mới mean |
|---|---|---|---|---|---|
| 1 | 30.99 | 161.1 | 124.5 / 213.0 / 145.8 | 614.0 | 204.0 |
| 3 | 10.74 | 5.976 | 7.58 / 1.00 / 9.35 | 20.79 | 6.857 |
| 10 | 3.59 | 0.5289 | 0.520 / 0.527 / 0.540 | 2.074 | 0.5758 |
| 30 | 1.47 | 0.4661 | 0.464 / 0.462 / 0.472 | 1.856 | 0.4989 |
| 100 | 0.62 | 0.4602 | 0.459 / 0.462 / 0.460 | 1.835 | 0.4839 |
| 1000 | 0.157 | 0.4483 | 0.447 / 0.449 / 0.449 | 1.777 | 0.4803 |
| không DP / none | — | 0.4432 | 0.443 / 0.443 / 0.443 | 1.754 | 0.4775 |

(Local: 0,4408; cửa hàng mới 0,4761.)

**Nhận xét.**
- Với ε ≤ 3, trung bình bị chi phối bởi seed xấu nhất (xem cột từng seed).
- Ngay cả ε = 1000 vẫn kém mô hình không DP (+1,2% WAPE) và kém Local.
- Với 3 client, nhiễu trên trung bình chỉ chia cho 3 nên DP rất tốn: không mức ε nào thử ở đây vừa có bảo đảm mạnh
  vừa bằng Local.
- Cần nhiều chuỗi hơn (nhiễu trên trung bình giảm theo 1/n) hoặc ít vòng hơn khi bật DP.

*With 3 clients DP is expensive; no tested ε gives both a strong guarantee and Local-level accuracy.*

## 8. Sử dụng / Usage

- `uv run python -m forecasting.fl train [--rounds 40] [--dp-epsilon E] [--clip-norm 0.3554] [--seed 0]` ghi ra
  `data/models/<chuỗi>.fl.npz/.json` (thân chung + đầu ra riêng + chuẩn hoá riêng + offset conformal riêng).
  - Lệnh `train` lấy cấu hình từ giá trị mặc định của `FLConfig` (40 × 1, lr 1e-3, `clip_norm` 0,3554); CLI chỉ
    đổi được số vòng, ε và ngưỡng cắt.
  - Mô hình đang triển khai (seed 0, không DP; cấu hình ghi trong `federated.config` của `.fl.json`) **tái lập
    đúng** các dòng `fl, seed 0` trong `fl_comparison.csv`. Mọi WAPE, pinball và độ phủ theo chuỗi và nhóm khớp
    đến ≤ 4e-6 (chỉ do làm tròn trong CSV). Chỉ số kiểm tra của mô hình triển khai (WAPE; pinball trong ngoặc):

    | Chuỗi | Tất cả | Cửa hàng mới |
    |---|---|---|
    | A | 0.3744 (1.459) | 0.4384 (1.404) |
    | B | 0.4578 (1.093) | — |
    | C | 0.4807 (2.519) | 0.4941 (2.899) |

    Đây là một seed. Kết luận ở mục 1 và 5 dựa trên trung bình 3 seed.
  - Thí nghiệm DP (mục 7) dùng ngưỡng cắt chưa làm tròn 0,35539 lấy trực tiếp từ `fl_tuning.csv`.
- `forecast_demand(..., model="fl")` hoặc biến môi trường `FRESHMESH_FORECAST_MODEL=fl` để dùng mô hình FL
  (mặc định vẫn là `local`).
- `forecasting.fl.fl_summary(data_dir, docs_dir)` trả dữ liệu cho `GET /api/network/fl`. Hàm đọc từ các CSV ở đây
  và báo lỗi rõ nếu chưa chạy thí nghiệm. Đầu ra hiện tại khớp các số ở mục 5 và 7.
