"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ClustersTab } from "@/components/ml/ClustersTab";
import { FaqTab } from "@/components/ml/FaqTab";
import { SupervisedTab } from "@/components/ml/SupervisedTab";
import { IconClock, IconPulse, IconUser } from "@/components/Icons";
import { Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { adminLogout, api, userLogout, type User } from "@/lib/api";
import type { Clusters, Workbench } from "@/lib/ml";

const TABS = [
  { id: "supervised", label: "Supervised" },
  { id: "clusters", label: "Clusters" },
  { id: "faq", label: "FAQ assistant" },
] as const;
type TabId = (typeof TABS)[number]["id"];

type Report<T> = { data: T | null; error: string | null };
const LOAD_ERROR = "This report could not be loaded right now. Please reload the page in a moment.";

/**
 * /ml: the Week 4 dashboard (educational demo on synthetic data).
 * Members (JWT) see all three tabs. An admin session only adds the policy upload on the FAQ tab: the reports and the
 * assistant are member endpoints, so an admin who is not also signed in as a member sees a "sign in as a member" note.
 * Nobody signed in -> /login, like the profile page.
 */
export default function MlPage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [member, setMember] = useState<User | null>(null);
  const [admin, setAdmin] = useState(false);
  const [tab, setTab] = useState<TabId>("supervised");
  const [workbench, setWorkbench] = useState<Report<Workbench>>({ data: null, error: null });
  const [clusters, setClusters] = useState<Report<Clusters>>({ data: null, error: null });
  const tabRefs = useRef<Record<TabId, HTMLButtonElement | null>>({ supervised: null, clusters: null, faq: null });

  useEffect(() => {
    (async () => {
      const [me, adminMe] = await Promise.allSettled([
        api<User>("/auth/me/"),
        api<User>("/admin/me/", { auth: "admin" }),
      ]);
      const isMember = me.status === "fulfilled";
      const isAdmin = adminMe.status === "fulfilled";
      if (!isMember && !isAdmin) {
        router.replace("/login");
        return;
      }
      setMember(isMember ? me.value : null);
      setAdmin(isAdmin);
      setChecked(true);
      if (!isMember) return;
      const [wb, cl] = await Promise.allSettled([
        api<Workbench>("/ml/v1/workbench/"),
        api<Clusters>("/ml/v1/clusters/"),
      ]);
      setWorkbench(wb.status === "fulfilled" ? { data: wb.value, error: null } : { data: null, error: LOAD_ERROR });
      setClusters(cl.status === "fulfilled" ? { data: cl.value, error: null } : { data: null, error: LOAD_ERROR });
    })().catch(() => setChecked(true));
  }, [router]);

  function choose(id: TabId, focus = false) {
    setTab(id);
    if (focus) tabRefs.current[id]?.focus();
  }

  function onTabKey(event: KeyboardEvent<HTMLButtonElement>) {
    const i = TABS.findIndex((t) => t.id === tab);
    const moves: Record<string, number> = {
      ArrowRight: (i + 1) % TABS.length, ArrowLeft: (i - 1 + TABS.length) % TABS.length, Home: 0, End: TABS.length - 1,
    };
    if (event.key in moves) {
      event.preventDefault();
      choose(TABS[moves[event.key]].id, true);
    }
  }

  async function signOut() {
    if (member) {
      await userLogout().catch(() => {});
      router.replace("/login");
    } else {
      await adminLogout().catch(() => {});
      router.replace("/admin/login");
    }
  }

  if (!checked) {
    return (
      <div className="main" style={{ maxWidth: 720, margin: "0 auto" }}>
        <div className="skeleton" style={{ width: 200, height: 28, marginBottom: 20 }} />
        <div className="skeleton" style={{ height: 220 }} />
      </div>
    );
  }

  const memberOnly = (content: React.ReactNode, report: Report<unknown>) => {
    if (!member) return <p className="card">Sign in as a member to see this report.</p>;
    if (report.error) return <div className="form-error" role="alert">{report.error}</div>;
    if (!report.data) return <div className="skeleton" style={{ height: 220 }} aria-label="Loading" />;
    return content;
  };

  return (
    <Shell
      nav={[
        { href: "/profile", label: "My profile", icon: <IconUser /> },
        { href: "/activity", label: "My activity", icon: <IconClock /> },
        { href: "/ml", label: "ML dashboard", icon: <IconPulse />, current: true },
      ]}
      box={
        <>
          <strong>Demo environment</strong>
          Synthetic data only. Educational, not medical advice.
        </>
      }
      onSignOut={signOut}
    >
      <header className="page-head">
        <div>
          <span className="eyebrow">Week 4 · educational demo</span>
          <h1>ML dashboard</h1>
          <p>Model comparison, exploratory clusters and an FAQ assistant, all on synthetic data.</p>
        </div>
        <ThemeToggle />
      </header>

      <div role="tablist" aria-label="ML dashboard sections" className="seg" style={{ marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => { tabRefs.current[t.id] = el; }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className="seg-item"
            // .seg-item styles aria-pressed; tabs use aria-selected, so the same colours are applied here.
            style={tab === t.id ? { background: "var(--primary)", borderColor: "var(--primary)", color: "var(--on-primary)" } : undefined}
            onClick={() => choose(t.id)}
            onKeyDown={onTabKey}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
        {tab === "supervised" && memberOnly(workbench.data && <SupervisedTab data={workbench.data} />, workbench)}
        {tab === "clusters" && memberOnly(clusters.data && <ClustersTab data={clusters.data} />, clusters)}
        {tab === "faq" && <FaqTab member={!!member} admin={admin} />}
      </div>
    </Shell>
  );
}
