"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  MessageSquare,
  BookOpen,
  Zap,
  Shield,
  Settings,
  LayoutDashboard,
  Menu,
  X,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

const sidebarVariants = {
  open: { width: "16rem" },
  closed: { width: "4rem" },
};

const itemVariants = {
  open: { x: 0, opacity: 1, transition: { x: { stiffness: 1000, velocity: -100 } } },
  closed: { x: -20, opacity: 0, transition: { x: { stiffness: 100 } } },
};

const transitionProps = { type: "tween" as const, ease: "easeOut" as const, duration: 0.2 };

interface NavItem {
  name: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  badge?: string;
}

const navigationItems: NavItem[] = [
  { name: "Dashboard", icon: LayoutDashboard, href: "/" },
  { name: "Chat", icon: MessageSquare, href: "/chat" },
  { name: "Knowledge", icon: BookOpen, href: "/knowledge" },
  { name: "Actions", icon: Zap, href: "/actions" },
  { name: "Admin", icon: Shield, href: "/admin", badge: "Dev" },
  { name: "Settings", icon: Settings, href: "/settings" },
];

interface EKCIPSidebarProps {
  systemOnline?: boolean;
}

export function EKCIPSidebar({ systemOnline = true }: EKCIPSidebarProps) {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = React.useState(true);
  const [isMobileOpen, setIsMobileOpen] = React.useState(false);

  React.useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) setIsMobileOpen(false);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <>
      <button
        onClick={() => setIsMobileOpen(!isMobileOpen)}
        className="md:hidden fixed top-4 left-4 z-50 p-2 rounded-lg bg-background border border-border shadow-lg hover:bg-muted transition-colors"
        aria-label="Toggle sidebar"
      >
        {isMobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {isMobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-30"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      <motion.aside
        className={cn(
          "fixed left-0 z-40 h-full shrink-0 border-r border-border bg-background",
          "transition-transform duration-300 ease-in-out",
          isMobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
        initial={isCollapsed ? "closed" : "open"}
        animate={isCollapsed ? "closed" : "open"}
        variants={sidebarVariants}
        transition={transitionProps}
        onMouseEnter={() => setIsCollapsed(false)}
        onMouseLeave={() => setIsCollapsed(true)}
      >
        <div className="flex h-full flex-col">
          <div className="flex h-[60px] shrink-0 border-b border-border p-3">
            <div className="flex w-full items-center gap-3">
              <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center shrink-0">
                <span className="text-primary-foreground font-bold text-sm">E</span>
              </div>
              {!isCollapsed && (
                <motion.div variants={itemVariants} initial="closed" animate="open">
                  <p className="text-sm font-semibold">EKCIP</p>
                  <p className="text-xs text-muted-foreground">Enterprise Platform</p>
                </motion.div>
              )}
            </div>
          </div>

          <ScrollArea className="flex-1 p-3">
            <nav className="flex flex-col gap-1">
              {navigationItems.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(item.href);

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsMobileOpen(false)}
                    className={cn(
                      "flex h-10 items-center rounded-md px-3 py-2 transition-colors hover:bg-muted",
                      isActive && "bg-muted text-primary",
                    )}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    {!isCollapsed && (
                      <motion.span
                        variants={itemVariants}
                        initial="closed"
                        animate="open"
                        className="ml-3 flex flex-1 items-center justify-between text-sm font-medium"
                      >
                        {item.name}
                        {item.badge && (
                          <Badge className="ml-auto bg-primary/10 text-primary border-primary/20 text-xs" variant="outline">
                            {item.badge}
                          </Badge>
                        )}
                      </motion.span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </ScrollArea>

          <motion.div className="border-t border-border p-3">
            <Separator className="mb-3" />
            <div className="flex items-center gap-3 px-3 py-2 rounded-md bg-muted/50">
              <div className="relative">
                <Activity className="h-5 w-5 shrink-0 text-muted-foreground" />
                <div
                  className={cn(
                    "absolute -top-1 -right-1 w-2 h-2 rounded-full border-2 border-background",
                    systemOnline ? "bg-green-500" : "bg-red-500",
                  )}
                />
              </div>
              {!isCollapsed && (
                <motion.div variants={itemVariants} initial="closed" animate="open">
                  <p className="text-xs font-medium">System Status</p>
                  <p className={cn("text-xs capitalize", systemOnline ? "text-green-600" : "text-red-600")}>
                    {systemOnline ? "online" : "offline"}
                  </p>
                </motion.div>
              )}
            </div>
          </motion.div>
        </div>
      </motion.aside>
    </>
  );
}
