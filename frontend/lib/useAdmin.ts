"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, adminLogout, api, type User } from "./api";

/** Loads the signed-in admin; sends the browser to /admin/login when there is no valid session. */
export function useAdmin() {
  const router = useRouter();
  const [admin, setAdmin] = useState<User | null>(null);

  useEffect(() => {
    api<User>("/admin/me/", { auth: "admin" })
      .then(setAdmin)
      .catch((err) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) router.replace("/admin/login");
      });
  }, [router]);

  async function signOut() {
    await adminLogout().catch(() => {});
    router.replace("/admin/login");
  }

  /** Call from a data request that fails with 401/403 (session expired after 30 idle minutes). */
  function handleSessionError(err: unknown): boolean {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      router.replace("/admin/login");
      return true;
    }
    return false;
  }

  return { admin, signOut, handleSessionError };
}
