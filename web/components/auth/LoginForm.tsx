"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, login } from "@/lib/api";
import { setSession, useSession } from "@/lib/session";
import { Spinner } from "@/components/ui/primitives";
import s from "./login.module.css";

export default function LoginForm() {
  const router = useRouter();
  const session = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ message: string; network: boolean } | null>(null);

  useEffect(() => {
    if (session) router.replace("/");
  }, [session, router]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError({ message: "Vui lòng nhập tên đăng nhập và mật khẩu.", network: false });
      return;
    }
    setPending(true);
    setError(null);
    try {
      const res = await login(username.trim(), password);
      setSession({ token: res.token, user: res.user });
      router.replace("/");
    } catch (err) {
      const network = err instanceof ApiError && err.isNetwork;
      const message =
        err instanceof ApiError && err.status === 401 && !network
          ? err.messageVi || "Sai tên đăng nhập hoặc mật khẩu."
          : errorMessage(err);
      setError({ message, network });
      setPending(false);
    }
  }

  return (
    <form className={s.form} onSubmit={onSubmit} noValidate>
      <div>
        <h2 id="login-title">Đăng nhập</h2>
        <p className={s.lead}>Mỗi chuỗi có không gian làm việc và dữ liệu riêng.</p>
      </div>

      <div className={s.field}>
        <label htmlFor="username">Tên đăng nhập</label>
        <input
          id="username"
          className="input"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          data-testid="login-username"
          aria-invalid={error && !error.network ? true : undefined}
        />
      </div>
      <div className={s.field}>
        <label htmlFor="password">Mật khẩu</label>
        <input
          id="password"
          type="password"
          className="input"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          data-testid="login-password"
          aria-invalid={error && !error.network ? true : undefined}
          aria-describedby={error ? "login-error" : undefined}
        />
      </div>

      {error ? (
        <p id="login-error" className={error.network ? s.errorNetwork : s.error} role="alert" data-testid="login-error">
          {error.message}
        </p>
      ) : null}

      <button type="submit" className={`btn btn-primary ${s.submit}`} disabled={pending} data-testid="login-submit">
        {pending ? <Spinner /> : null}
        {pending ? "Đang đăng nhập" : "Đăng nhập"}
      </button>

      <div className={s.hint}>
        <p>Tài khoản demo (mật khẩu <code>demo123</code>):</p>
        <ul>
          <li>
            <code>owner_a</code> chủ chuỗi A, xem toàn chuỗi
          </li>
          <li>
            <code>manager_a1</code> quản lý một cửa hàng, quyền duyệt giới hạn
          </li>
        </ul>
        <p>Tương tự cho chuỗi B, C: owner_b, manager_b1, owner_c, manager_c1.</p>
      </div>
    </form>
  );
}
