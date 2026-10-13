# FreshMesh — Design System & UI/UX Specification

> Source of Truth: [`docs/superpowers/specs/2026-10-12-freshmesh-design.md`](file:///home/tta/projects/freshmesh/docs/superpowers/specs/2026-10-12-freshmesh-design.md) and [`docs/superpowers/plans/2026-10-12-routing-adapter.md`](file:///home/tta/projects/freshmesh/docs/superpowers/plans/2026-10-12-routing-adapter.md).

## 1. Core Principles

- **Human-in-the-loop**: The system proposes, human decides ("Duyệt / Sửa / Bỏ").
- **Language**: Vietnamese for all user-facing strings, prompts, labels, and errors; English for identifiers, code symbols, and logs.
- **Transparency**: Every simulation, heuristic, or forecasted metric MUST be labeled clearly (`SIMULATED`, sources, confidence intervals).
- **Graceful Failure**: Never hallucinate or synthesize fake routes or numbers. When a solver fails or an order cannot be met, report clear Vietnamese reasons and flag at-risk orders.

## 2. CLI UI/UX Guidelines (Plan 1)

The CLI tool (`routing.cli`) formats route plans for human operators:
- **Header**:
  - `FreshMesh — lộ trình đợt giao (dữ liệu: SIMULATED)`
  - `Cửa hàng: <store_id> | Solver: <SOLVER> | Thời gian giải: <runtime>s`
  - `Xe dùng: <count> (VƯỢT số xe hiện có if exceeds_fleet)`
  - `Quãng đường ước tính: <km> km (đã gồm hệ số đường vòng)`
  - `So với mỗi đơn một chuyến: <baseline_km> km → tiết kiệm <saving>%`
- **Route Breakdown**:
  - `Xe <index>: <order_id> (<destination_kind>, ETA +<eta>')[ ⚠ trễ] → ...`
  - Destination kind: `tận nhà` for home delivery, `điểm nhận <pickup_point_id>` for locker/counter.
- **At-Risk Warning Section**:
  - `Đơn có nguy cơ (không đưa vào lộ trình, cần bạn xử lý):`
  - Detailed Vietnamese reason per order:
    - `invalid_demand`: "số lượng không hợp lệ"
    - `over_capacity`: "vượt tải một xe"
    - `window_closed`: "khung giờ đã qua"
    - `unreachable_in_window`: "không kịp giao trong khung giờ"
    - `unknown_pickup_point`: "điểm nhận không tồn tại"
- **Footer**:
  - `Giả định: tốc độ trung bình và hệ số đường vòng là ước tính; bạn duyệt trước khi gửi cho shipper.`

## 3. Web UI Specification (Future Plans)

- **Layout**: Two-pane split dashboard:
  - Left pane: Conversational AI agent, action proposal cards with "Duyệt / Sửa / Bỏ" action buttons, audit trail.
  - Right pane: Contextual analytical dashboard (P10-P90 forecast bands, interactive Leaflet/OSM route map with vehicle paths and locker nodes, trust badges, data assumption tabs).
- **Tone & Typography**: Clean, high-density, professional supply-chain interface.
- **Color Palette**:
  - Primary: Forest / Fresh Green (representing fresh goods efficiency).
  - Surface: Dark slate or clean light mode depending on theme.
  - Accent / Status: Amber for warnings / at-risk orders, Red for critical SLA breaches, Blue for lockers / pickup points.
