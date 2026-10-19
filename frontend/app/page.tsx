"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";

/** Landing: signed-in members go to their profile, everyone else to sign in. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    api("/auth/me/")
      .then(() => router.replace("/profile"))
      .catch(() => router.replace("/login"));
  }, [router]);
  return null;
}
