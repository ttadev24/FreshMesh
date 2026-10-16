"use client";

import Image from "next/image";
import type { ComponentType } from "react";
import { ROLE_VI } from "@/lib/format";
import type { User } from "@/lib/types";
import { NAV_MAIN, NAV_SOURCES, type NavId } from "./nav";
import { BasketIcon, BoxIcon, HistoryIcon, HomeIcon, LogoutIcon, MeshIcon, SourcesIcon, TruckIcon } from "./shell-icons";
import s from "./shell.module.css";

const ICONS: Record<NavId, ComponentType<{ size?: number }>> = {
  overview: HomeIcon,
  import: BasketIcon,
  stock: BoxIcon,
  delivery: TruckIcon,
  network: MeshIcon,
  history: HistoryIcon,
  sources: SourcesIcon,
};

interface Props {
  nav: NavId;
  onNav: (id: NavId) => void;
  user: User;
  onLogout: () => void;
}

function initials(name: string): string {
  const parts = name.replace(/[_.-]+/g, " ").trim().split(/\s+/);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
}

export default function Sidebar({ nav, onNav, user, onLogout }: Props) {
  const item = (id: NavId, label: string) => {
    const Icon = ICONS[id];
    return (
      <button
        key={id}
        type="button"
        className={s.navItem}
        aria-current={nav === id ? "page" : undefined}
        onClick={() => onNav(id)}
        data-testid={`nav-${id}`}
      >
        <Icon />
        <span className={s.navLabel}>{label}</span>
      </button>
    );
  };

  return (
    <aside className={s.sidebar} aria-label="Điều hướng chính">
      <div className={s.sideBrand}>
        <Image src="/brand/freshmesh-logo.png" alt="" width={38} height={37} priority />
        <span>FreshMesh</span>
      </div>

      <nav className={s.nav}>{NAV_MAIN.map((n) => item(n.id, n.label))}</nav>

      <div className={s.sideFoot}>
        {item(NAV_SOURCES.id, NAV_SOURCES.label)}
        <div className={s.userRow}>
          <span className={s.avatar} aria-hidden="true">
            {initials(user.username)}
          </span>
          <span className={s.userText} data-testid="user-role">
            <span className={s.userName}>{user.username}</span>
            <span className={s.userRole}>{ROLE_VI[user.role] ?? user.role}</span>
          </span>
          <button type="button" className={s.logout} onClick={onLogout} data-testid="logout" aria-label="Đăng xuất" title="Đăng xuất">
            <LogoutIcon size={20} />
          </button>
        </div>
      </div>
    </aside>
  );
}
