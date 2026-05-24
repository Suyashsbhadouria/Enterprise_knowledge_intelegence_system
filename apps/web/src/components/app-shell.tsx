"use client";

import * as React from "react";
import { EKCIPSidebar } from "@/components/app-sidebar";
import { api } from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [systemOnline, setSystemOnline] = React.useState(true);

  React.useEffect(() => {
    api.healthLive()
      .then(() => setSystemOnline(true))
      .catch(() => setSystemOnline(false));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <EKCIPSidebar systemOnline={systemOnline} />
      <main className="md:ml-16 min-h-screen transition-all duration-300">
        <div className="p-6 md:p-8 pt-16 md:pt-8 max-w-7xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
