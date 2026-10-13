const TOOL_LABEL_VI: Record<string, string> = {
  forecast_demand: "Dự báo nhu cầu P10, P50, P90",
  plan_inventory: "Lập 3 phương án nhập hàng",
  suggest_markdown: "Tính lịch giảm giá theo khung giờ",
  transfer_stock: "Tính phương án điều chuyển",
  compare_markdown_vs_transfer: "So sánh giảm giá với điều chuyển",
  optimize_routes: "Tối ưu lộ trình giao (PACO)",
  plan_routes: "Tối ưu lộ trình giao (PACO)",
  query_data: "Truy vấn dữ liệu chỉ đọc",
  render_chart: "Dựng biểu đồ",
  drift_status: "Kiểm tra độ lệch dự báo",
  create_purchase_order: "Tạo bản nháp đơn đặt hàng",
  apply_markdown: "Tạo bản nháp giảm giá",
  create_transfer: "Tạo bản nháp điều chuyển",
  dispatch_routes: "Tạo bản nháp gửi lộ trình",
};

export function toolLabel(name: string, description?: string): string {
  return TOOL_LABEL_VI[name] ?? (description ? description.split(/[.;]/)[0] : name);
}
