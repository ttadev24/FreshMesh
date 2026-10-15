# Tích hợp Jev (TypeSafe AI) — Thiết kế

> Jev: mô hình quyết định của TypeSafe, gọi qua OpenRouter (`POST /api/alpha/decisions`), trả về xác suất
> cho câu hỏi dạng có/không (`noul`), chọn 1 trong nhiều lựa chọn (`choice`) hoặc thang điểm (`score`). Jev
> không viết văn bản, không thay thế bất kỳ phép tính nào hiện có trong FreshMesh.

- Ngày: 2026-10-15
- Trạng thái: chờ duyệt
- Động lực: không phải yêu cầu đề bài; chủ dự án muốn dùng Jev vì là công nghệ mới, miễn là mang lại giá
  trị thật, không phải chỉ để "có cho có".

## 1. Bối cảnh và mục tiêu

### 1.1 Nguyên tắc phải giữ
FreshMesh đã có 2 nguyên tắc không được vi phạm khi thêm Jev (`DESIGN.md`, `agent/guardrail.py`):
- Không bịa số: mọi con số trong câu trả lời phải truy được về kết quả công cụ thật.
- Máy chỉ đề xuất, người duyệt mới thực thi.

Jev **không** được dùng để tính toán số liệu hiển thị cho người dùng (dự báo, tồn kho, lộ trình...) — chỉ
dùng để **đánh giá/phân loại văn bản hoặc tình huống đã có sẵn**, giữ vai trò lớp giám sát/gợi ý phụ, không
phải nguồn số liệu.

### 1.2 Phạm vi: 5 tính năng, 1 nền chung
1. Kiểm tra câu trả lời của agent (có tự nhận đã thực thi khi chỉ là bản nháp không).
2. Sổ ghi lại Jev đã bắt lỗi gì (mở rộng tab "Lịch sử quyết định").
3. Xếp ưu tiên bản nháp chờ duyệt.
4. Nhắc "cửa hàng nào cần xem hôm nay" (owner nhiều cửa hàng).
5. Ý kiến tham khảo khi cửa hàng/SKU mới chưa đủ dữ liệu dự báo.

Thứ tự triển khai: 1 → 2 → 3 → 4 → 5 (rẻ/an toàn trước, tốn công/rủi ro sau). Mỗi tính năng có cờ bật/tắt
riêng, **mặc định tắt**.

### 1.3 Ngoài phạm vi
- Thay thế bất kỳ phép tính nào hiện có (dự báo, Monte Carlo, PACO, conformal).
- Dùng Jev để tự động thực thi hành động (vẫn phải qua `POST /api/drafts/{id}/approve`).
- Giao diện quản trị để đổi câu hỏi Jev lúc chạy (cấu hình nằm trong code).

## 2. Kiến trúc

### 2.1 Module nền: `agent/jev.py`
```python
def ask_jev(state: str, questions: dict[str, JevQuestion]) -> dict[str, JevAnswer] | None
```
- Đọc `FRESHMESH_JEV_API_KEY` (bắt buộc để bật), `FRESHMESH_JEV_MODEL` (mặc định `typesafe/jev-1.13`).
- Gọi `POST https://openrouter.ai/api/alpha/decisions`, timeout ngắn (5s).
- **Không bao giờ raise**: thiếu key, lỗi mạng, timeout, HTTP lỗi, JSON lạ → trả `None`. Mọi nơi gọi
  `ask_jev` phải coi `None` như "Jev không khả dụng, chạy tiếp như chưa có Jev" — không chặn, không báo lỗi
  cho người dùng.
- Dữ liệu gửi đi phải qua `agent.guardrail.redact_for_llm` trước (Jev là bên thứ ba, cùng quy tắc với
  Claude).

### 2.2 Cờ bật/tắt (theo đúng kiểu `FRESHMESH_ENABLE_DOCS` đã có)
| Biến môi trường | Tính năng |
|---|---|
| `FRESHMESH_JEV_GUARDRAIL` | 1. Kiểm tra câu trả lời |
| `FRESHMESH_JEV_DRAFT_PRIORITY` | 3. Ưu tiên bản nháp |
| `FRESHMESH_JEV_STORE_DIGEST` | 4. Cửa hàng cần xem hôm nay |
| `FRESHMESH_JEV_LOW_DATA_OPINION` | 5. Ý kiến khi thiếu dữ liệu |

(Tính năng 2 — sổ ghi log — luôn bật cùng tính năng 1, không cần cờ riêng: chỉ ghi khi 1 thực sự chạy.)

## 3. Chi tiết từng tính năng

### 3.1 Kiểm tra câu trả lời agent
- Vị trí: `agent/loop.py`, trong `AgentSession._verify_and_answer`, sau khi đã có `claims_execution(text)`.
- Câu hỏi Jev (`noul`): "Câu trả lời có khẳng định một hành động thật (đặt hàng, gửi lộ trình, giảm giá,
  điều chuyển) ĐÃ được thực hiện, thay vì chỉ tạo bản nháp chờ duyệt?" — `state` = văn bản câu trả lời (đã
  redact).
- Nếu bật và `ask_jev` trả về `noul >= 0.5`: thêm vào `problems` y như nhánh `claims` hiện có → kích hoạt
  lại đúng cơ chế "viết lại" đã tồn tại (`REWRITE_PROMPT_VI`). Không tạo luồng rewrite mới.
- Nếu Jev không khả dụng hoặc tắt: hành vi y hệt hiện tại (chỉ `claims_execution`).
- Chạy **song song** với, không thay thế, `claims_execution()` và `verify_numbers()`.

### 3.2 Sổ ghi lại Jev đã bắt lỗi gì
- Thêm sự kiện mới vào `agent/audit.py`: mở rộng `EVENTS` thêm `"jev_flag"`.
- Mỗi lần 3.1 kích hoạt rewrite do Jev, ghi `audit.log_jev_flag(chain_id, actor, turn_id, probability,
  problem_vi)`.
- Web: `web/components/tabs/AuditTab.tsx` thêm 1 nút lọc "Jev can thiệp" cạnh 3 nút đã có (`Tất cả`, `Quyết
  định duyệt / bỏ`, `Hoạt động trợ lý`), lọc `event=jev_flag`. Không cần trang mới.

### 3.3 Xếp ưu tiên bản nháp
- Vị trí: `api/main.py` `create_draft` (hoặc trong `registry.call` cho mọi tool kind=`draft`), sau khi
  draft đã tạo thành công.
- Câu hỏi Jev (`score`, 4 mức: `bình thường` / `nên xem sớm` / `gấp` / `rất gấp`) dựa trên tóm tắt nội dung
  draft (loại draft, số tiền, có hàng sắp hết hạn trong vài giờ không — lấy từ payload, không để Jev tự
  suy ra số).
- Lưu kết quả vào `payload_json` của draft dưới khóa `jev_priority` (JSON blob sẵn có, không đổi schema
  bảng `drafts`).
- Web: `PanelDrafts.tsx` / `ProposalCard.tsx` hiện nhãn nhỏ khi `jev_priority` ở mức `gấp`/`rất gấp`.

### 3.4 Cửa hàng cần xem hôm nay
- Chỉ áp dụng khi `user.is_owner` (nhiều cửa hàng).
- Endpoint mới `GET /api/stores/digest`: với mỗi cửa hàng của chuỗi, gom tín hiệu đã có sẵn (số bản nháp
  chờ duyệt, số đơn nguy cơ của lộ trình đã cache gần nhất nếu có, cờ hàng sắp hết hạn) → hỏi Jev chấm điểm
  mức cần xem mỗi cửa hàng.
- Web: 1 khu vực mới trên `DashboardOverview.tsx` (hoặc gần bộ chọn cửa hàng ở header), chỉ hiện với owner.
- Đây là phần tốn công nhất: cần endpoint mới + logic gom dữ liệu nhiều cửa hàng + 1 vùng giao diện mới.

### 3.5 Ý kiến khi thiếu dữ liệu
- Vị trí: `forecasting/confidence.py`, nhánh khi `store_history_days < SHORT_HISTORY_DAYS` (độ tin cậy đã
  là "Thấp").
- Câu hỏi Jev (`choice`, các mức số lượng nhập thử gợi ý) dựa trên state mô tả tình huống (cửa hàng mới,
  SKU nào, giá, nhóm hàng).
- **Ràng buộc bắt buộc**: kết quả gắn `source_kind="ai_generated"` (nhãn có sẵn trong `provenance/registry`,
  mô tả đúng "cần đối chiếu trước khi dùng thật"), và **phải nằm trong `NON_SOURCE_KEYS`** của
  `agent/guardrail.py` để không bị `verify_numbers` dùng làm căn cứ xác minh số thật. Hiển thị kèm dòng "ý
  kiến AI, không phải số đã tính toán" ngay cạnh, không gộp chung với P10/P50/P90.
- Việc này đụng tới nguyên tắc cốt lõi của dự án nên cần review kỹ nhất trong 5 tính năng.

## 4. Xử lý lỗi / suy giảm nhẹ nhàng
- Thiếu `FRESHMESH_JEV_API_KEY`: `/api/health` thêm trường `jev: false`; mọi tính năng ở trên tắt, hệ thống
  chạy y như chưa từng có Jev.
- Lỗi mạng / timeout / HTTP lỗi từ OpenRouter: `ask_jev` trả `None`, log cảnh báo (không phải lỗi), tính
  năng gọi nó bỏ qua bước Jev cho lượt đó.
- Không bao giờ để một lần gọi Jev làm chậm hoặc chặn luồng chính quá ngưỡng (timeout 5s là giới hạn cứng).

## 5. Kiểm thử
- `agent/jev.py`: test với client giả (theo mẫu `tests/agent/fake_llm.py`), không gọi mạng thật trong unit
  test — khớp quy ước hiện có (`tests/` dùng client giả, chỉ `agent/eval.py --client anthropic` mới tốn
  tiền thật).
- Mỗi tính năng: test "Jev tắt/lỗi" (hành vi không đổi) và "Jev bật, trả kết quả giả định" (hành vi đúng
  như thiết kế) — không có test nào gọi Jev thật.
- Việc gọi Jev thật (xác nhận hiểu tiếng Việt) chỉ chạy thủ công, có xác nhận của người dùng trước mỗi lần,
  không đưa vào bộ test tự động.

## 6. Thứ tự triển khai và điểm dừng duyệt
Mỗi tính năng (3.1–3.5) là một đợt làm riêng, merge/duyệt xong mới sang tính năng kế — không làm gộp. Sau
tính năng 1, dừng lại xác nhận kết quả Jev đoán tiếng Việt tốt không rồi mới tiếp tục.
