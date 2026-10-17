import type { Metadata } from "next";
import Image from "next/image";
import LoginScreen from "@/components/auth/LoginScreen";
import { HelpIcon } from "@/components/auth/login-icons";
import s from "@/components/auth/login.module.css";
import { REPO_URL } from "@/lib/repo";

export const metadata: Metadata = { title: "Đăng nhập · FreshMesh" };

export default function LoginPage() {
  return (
    <div className={s.page}>
      <header className={s.header}>
        <span className={s.brand}>
          <Image src="/brand/freshmesh-logo.png" alt="" width={46} height={45} priority />
          FreshMesh
        </span>
        <a className={s.help} href={`${REPO_URL}#readme`} target="_blank" rel="noreferrer">
          <HelpIcon size={26} />
          Hỗ trợ
        </a>
      </header>

      <LoginScreen repoUrl={REPO_URL} />

      <footer className={s.footer}>
        <span>© FreshMesh</span>
        <details className={s.privacy}>
          <summary>Quyền riêng tư</summary>
          <p>
            Bản demo không chứa dữ liệu khách hàng thật: đơn hàng và doanh số do chương trình sinh, vị trí cửa hàng lấy
            từ OpenStreetMap. Phiên đăng nhập chỉ lưu trên trình duyệt của bạn.
          </p>
        </details>
      </footer>
    </div>
  );
}
