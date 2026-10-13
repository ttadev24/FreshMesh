"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "@/lib/session";
import { Skeleton } from "@/components/ui/primitives";
import WorkspaceShell from "./WorkspaceShell";
import s from "./workspace.module.css";

/** Client-side guard: the token lives in memory / sessionStorage, which a server proxy cannot read. */
export default function Workspace() {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session === null) router.replace("/login");
  }, [session, router]);

  if (!session) {
    return (
      <div className={s.boot}>
        <Skeleton lines={4} label="Đang kiểm tra phiên đăng nhập" />
      </div>
    );
  }
  // Keyed on the user: with cacheComponents, routes stay mounted (Activity), so a re-login as another
  // user must not inherit the previous conversation.
  return <WorkspaceShell key={session.user.user_id} user={session.user} />;
}
