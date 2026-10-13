import type { Metadata } from "next";
import LoginForm from "@/components/auth/LoginForm";
import s from "@/components/auth/login.module.css";
import { SimulatedBadge } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Đăng nhập · FreshMesh" };

export default function LoginPage() {
  return (
    <main className={s.page}>
      <section className={s.brand} aria-labelledby="brand-title">
        <div className={s.brandTop}>
          <span className={s.logo} aria-hidden="true">
            FM
          </span>
          <SimulatedBadge />
        </div>
        <div className={s.brandBody}>
          <h1 id="brand-title">FreshMesh</h1>
          <p>
            Trợ lý quyết định cho chuỗi mini-mart: dự báo nhu cầu hàng tươi, đề xuất nhập hàng, xử lý tồn và gom đơn giao
            hàng. Hệ thống chỉ đề xuất, bạn là người duyệt.
          </p>
          <ul className={s.flows}>
            <li>
              <b>Sáng</b> Nhập hàng theo dự báo P10 đến P90
            </li>
            <li>
              <b>Chiều</b> Giảm giá theo giờ hay điều chuyển tồn
            </li>
            <li>
              <b>Online</b> Gom đơn, lộ trình nhiều xe, tủ nhận hàng
            </li>
          </ul>
        </div>
        <p className={s.brandFoot}>Dữ liệu trong bản demo là dữ liệu giả lập, đã ghi rõ giả định.</p>
      </section>
      <section className={s.formWrap} aria-labelledby="login-title">
        <LoginForm />
      </section>
    </main>
  );
}
