"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import LoginForm from "./LoginForm";
import { ArrowUpRightIcon, PinIcon, RouteIcon, SunIcon, TagIcon } from "./login-icons";
import s from "./login.module.css";

// Rotating caption on the hero photo; the dots under the form show and pick the current one.
const SLIDES = [
  { Icon: PinIcon, text: "Kết nối cửa hàng. Giữ trọn độ tươi." },
  { Icon: SunIcon, text: "Sáng: nhập vừa đủ theo dự báo nhu cầu." },
  { Icon: TagIcon, text: "Chiều: giảm giá hay điều chuyển, so bằng tiền." },
  { Icon: RouteIcon, text: "Online: gom đơn, tối ưu lộ trình giao." },
];
const ROTATE_MS = 6000;

export default function LoginScreen({ repoUrl }: { repoUrl: string }) {
  const [slide, setSlide] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Restarts whenever the slide changes, so a click on a dot gets a full interval.
    const id = window.setTimeout(() => setSlide((i) => (i + 1) % SLIDES.length), ROTATE_MS);
    return () => window.clearTimeout(id);
  }, [slide]);

  const { Icon, text } = SLIDES[slide];

  return (
    <main className={s.main}>
      <section className={s.hero} aria-label="Giới thiệu FreshMesh">
        <Image
          src="/login/fresh-produce-crate.webp"
          alt=""
          fill
          priority
          sizes="(max-width: 960px) 100vw, 60vw"
          className={s.heroImg}
        />
        <div className={s.heroShade} aria-hidden="true" />
        <div className={s.heroTop}>
          <p className={s.eyebrow}>Fresh retail, connected</p>
          <a
            className={s.heroLink}
            href={repoUrl}
            target="_blank"
            rel="noreferrer"
            aria-label="Tìm hiểu FreshMesh (mở GitHub trong thẻ mới)"
          >
            <ArrowUpRightIcon size={24} />
          </a>
        </div>
        <p className={s.headline}>
          Tươi mỗi ngày.
          <br />
          Chủ động từng bước.
        </p>
        <p key={slide} className={s.caption} aria-live="polite">
          <Icon size={22} />
          {text}
        </p>
      </section>

      <section className={s.card} aria-labelledby="login-title">
        <LoginForm />
        <div className={s.dots} role="group" aria-label="Chọn thông điệp giới thiệu">
          {SLIDES.map((item, i) => (
            <button
              key={item.text}
              type="button"
              className={s.dot}
              aria-label={`Thông điệp ${i + 1}: ${item.text}`}
              aria-pressed={i === slide}
              onClick={() => setSlide(i)}
            />
          ))}
        </div>
      </section>
    </main>
  );
}
