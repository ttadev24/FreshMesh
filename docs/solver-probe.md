# Kết quả đo Runtime Solver PACO (routing-PL)

Tài liệu ghi lại kết quả đo hiệu năng của solver PACO theo kích thước đợt đơn (`probe_solver.py`), tuân thủ Task 7 trong kế hoạch triển khai adapter định tuyến.

## 1. Thông số môi trường thử nghiệm

- **CPU (`nproc`)**: 16 cores
- **RAM**: 31 GiB (Free/Available: ~12-16 GiB)
- **Submodule `routing-PL` commit**: `32488ce`
- **Container image**: `freshmesh-solver:routing-pl-32488ce`
- **Hệ điều hành**: Linux (x86_64)
- **Python**: 3.13 (container solver) / 3.13.15 (host virtualenv)

## 2. Kết quả đo đạc (Runtime Benchmark)

| orders | size | wall s (median) | solver s (median) | km (median) | vehicles |
|---|---|---|---|---|---|
| 25 | small | 1.2 | 1.2 | 49.7 | 4 |
| 50 | medium | 35.6 | 35.6 | 81.7 | 9 |
| 100 | large | 245.4 | 245.4 | 144.3 | 18 |

## 3. Quyết định giới hạn kích thước đợt đơn (`max_orders_per_batch`)

Áp dụng quy tắc cố định được định nghĩa trong Plan 1:
- Nếu wall time median với 100 đơn ≤ 120 giây: giữ `max_orders_per_batch = 100`.
- Nếu wall time median với 100 đơn > 120 giây: đặt `max_orders_per_batch` bằng kích thước lớn nhất trong `{25, 50}` có median ≤ 120 giây.

### Kết luận
- Với 100 đơn, wall time đo được là **245.4 giây** (> 120 giây và tiệm cận giới hạn cứng 300 giây của FastAPI service).
- Với 50 đơn, wall time là **35.6 giây** (đạt tiêu chuẩn ≤ 120 giây để đợt gom 30 phút trả kết quả đủ sớm cho điều phối).
- Do đó, giá trị mặc định của `RoutingConfig.max_orders_per_batch` được cập nhật thành **`50`** trong `routing/config.py`.
- Toàn bộ 36 unit tests và 1 integration test đều đã được xác minh vượt qua với giới hạn mới này.
