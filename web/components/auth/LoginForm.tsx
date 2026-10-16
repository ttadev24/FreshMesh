"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, login } from "@/lib/api";
import { setSession, useSession } from "@/lib/session";
import { Spinner } from "@/components/ui/primitives";
import { ArrowRightIcon, EyeIcon, EyeOffIcon } from "./login-icons";
import s from "./login.module.css";

// Public demo account, prefilled so visitors can sign in with one click ("Quên mật khẩu?" lists the others).
const DEMO_USERNAME = "owner_a";
const DEMO_PASSWORD = "demo123";

export default function LoginForm() {
  const router = useRouter();
  const session = useSession();
  const [username, setUsername] = useState(DEMO_USERNAME);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [showDemo, setShowDemo] = useState(false);
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
      setSession({ token: res.token, user: res.user }, { remember });
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

  const invalid = error && !error.network ? true : undefined;

  return (
    <form className={s.form} onSubmit={onSubmit} noValidate>
      <div>
        <h1 id="login-title" className={s.title}>
          Đăng nhập
        </h1>
        <p className={s.lead}>Chào mừng bạn trở lại.</p>
      </div>

      <div className={s.field}>
        <label htmlFor="username">Tên đăng nhập</label>
        <input
          id="username"
          className={s.input}
          placeholder="Nhập tên đăng nhập"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          data-testid="login-username"
          aria-invalid={invalid}
        />
      </div>
      <div className={s.field}>
        <label htmlFor="password">Mật khẩu</label>
        <div className={s.pw}>
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            className={s.input}
            placeholder="Nhập mật khẩu"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="login-password"
            aria-invalid={invalid}
            aria-describedby={error ? "login-error" : undefined}
          />
          <button
            type="button"
            className={s.eye}
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
            aria-pressed={showPassword}
          >
            {showPassword ? <EyeOffIcon size={22} /> : <EyeIcon size={22} />}
          </button>
        </div>
      </div>

      <div className={s.row}>
        <label className={s.check}>
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Ghi nhớ đăng nhập
        </label>
        <button
          type="button"
          className={s.linkBtn}
          onClick={() => setShowDemo((v) => !v)}
          aria-expanded={showDemo}
          aria-controls="demo-accounts"
        >
          Quên mật khẩu?
        </button>
      </div>

      {showDemo ? (
        <p id="demo-accounts" className={s.note}>
          Đây là bản demo: mọi tài khoản dùng mật khẩu <code>{DEMO_PASSWORD}</code>. Chủ chuỗi: <code>owner_a</code>,{" "}
          <code>owner_b</code>, <code>owner_c</code>. Quản lý cửa hàng: <code>manager_a1</code>, <code>manager_b1</code>
          , <code>manager_c1</code>.
        </p>
      ) : null}

      {error ? (
        <p id="login-error" className={error.network ? s.errorNetwork : s.error} role="alert" data-testid="login-error">
          {error.message}
        </p>
      ) : null}

      <button type="submit" className={s.submit} disabled={pending} data-testid="login-submit">
        {pending ? <Spinner /> : null}
        {pending ? "Đang đăng nhập" : "Đăng nhập"}
        <span className={s.arrow}>
          <ArrowRightIcon size={24} />
        </span>
      </button>
    </form>
  );
}
