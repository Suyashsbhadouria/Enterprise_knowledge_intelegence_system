"use client";

import * as React from "react";
import { motion, useAnimation, useInView } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  RefreshCw,
  FileText,
  Code2,
  Hash,
  Video,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export interface MetricCardData {
  id: string;
  source: string;
  icon: React.ReactNode;
  entityCount: number;
  entityLabel: string;
  status: "connected" | "disconnected" | "syncing";
  lastSync?: string;
  color: string;
}

interface MetricCardProps {
  data: MetricCardData;
  onSync?: (id: string) => void;
}

function GridPattern({
  width,
  height,
  x,
  y,
  squares,
  ...props
}: React.ComponentProps<"svg"> & {
  width: number;
  height: number;
  x: string;
  y: string;
  squares?: number[][];
}) {
  const patternId = React.useId();

  return (
    <svg aria-hidden="true" {...props}>
      <defs>
        <pattern id={patternId} width={width} height={height} patternUnits="userSpaceOnUse" x={x} y={y}>
          <path d={`M.5 ${height}V.5H${width}`} fill="none" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" strokeWidth={0} fill={`url(#${patternId})`} />
      {squares && (
        <svg x={x} y={y} className="overflow-visible">
          {squares.map(([sx, sy], index) => (
            <rect strokeWidth="0" key={index} width={width + 1} height={height + 1} x={sx * width} y={sy * height} />
          ))}
        </svg>
      )}
    </svg>
  );
}

function genRandomPattern(length = 5): number[][] {
  return Array.from({ length }, () => [
    Math.floor(Math.random() * 4) + 7,
    Math.floor(Math.random() * 6) + 1,
  ]);
}

const MetricCard: React.FC<MetricCardProps> = ({ data, onSync }) => {
  const cardRef = React.useRef<HTMLDivElement>(null);
  const isInView = useInView(cardRef, { once: true, amount: 0.3 });
  const controls = useAnimation();
  const [pattern] = React.useState(() => genRandomPattern());

  React.useEffect(() => {
    if (isInView) controls.start("visible");
  }, [isInView, controls]);

  const getStatusBadge = () => {
    switch (data.status) {
      case "connected":
        return (
          <Badge className="bg-emerald-50 border-emerald-200 text-emerald-700 dark:bg-emerald-950 dark:border-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Connected
          </Badge>
        );
      case "disconnected":
        return (
          <Badge className="bg-rose-50 border-rose-200 text-rose-700 dark:bg-rose-950 dark:border-rose-800 dark:text-rose-300">
            <XCircle className="w-3 h-3 mr-1" />
            Disconnected
          </Badge>
        );
      case "syncing":
        return (
          <Badge className="bg-sky-50 border-sky-200 text-sky-700 dark:bg-sky-950 dark:border-sky-800 dark:text-sky-300">
            <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
            Syncing
          </Badge>
        );
    }
  };

  return (
    <motion.div
      ref={cardRef}
      initial="hidden"
      animate={controls}
      variants={{
        hidden: { opacity: 0, y: 20 },
        visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
      }}
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
      className="relative overflow-hidden p-6 rounded-lg border bg-card shadow-sm hover:shadow-md transition-shadow"
    >
      <div className="pointer-events-none absolute top-0 left-1/2 -mt-2 -ml-20 h-full w-full [mask-image:linear-gradient(white,transparent)]">
        <div className="from-foreground/5 to-foreground/1 absolute inset-0 bg-gradient-to-r opacity-100">
          <GridPattern
            width={20}
            height={20}
            x="-12"
            y="4"
            squares={pattern}
            className="fill-foreground/5 stroke-foreground/25 absolute inset-0 h-full w-full mix-blend-overlay"
          />
        </div>
      </div>

      <div className="relative z-10 flex flex-col gap-4">
        <div className="flex items-start justify-between">
          <div className="p-3 rounded-lg" style={{ backgroundColor: `${data.color}15` }}>
            <div style={{ color: data.color }}>{data.icon}</div>
          </div>
          {getStatusBadge()}
        </div>

        <div>
          <h3 className="text-lg font-semibold text-card-foreground">{data.source}</h3>
          <p className="text-sm text-muted-foreground mt-1">
            {data.lastSync ?? "Never synced"}
          </p>
        </div>

        <div className="flex items-end justify-between">
          <div>
            <div className="text-3xl font-bold text-card-foreground">
              {data.entityCount.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground mt-1">{data.entityLabel}</p>
          </div>

          <Button
            size="sm"
            variant="outline"
            onClick={() => onSync?.(data.id)}
            disabled={data.status === "syncing" || data.status === "disconnected"}
            className="gap-2"
          >
            <RefreshCw className={cn("w-4 h-4", data.status === "syncing" && "animate-spin")} />
            Sync
          </Button>
        </div>
      </div>
    </motion.div>
  );
};

interface MetricGridProps {
  title?: string;
  description?: string;
  metrics: MetricCardData[];
  onSync?: (id: string) => void;
}

export function MetricGrid({
  title = "Data Sources",
  description = "Monitor and manage your connected data sources",
  metrics,
  onSync,
}: MetricGridProps) {
  return (
    <section className="w-full">
      <div className="mb-8">
        <h2 className="text-2xl font-bold tracking-tight text-foreground mb-2">{title}</h2>
        <p className="text-muted-foreground">{description}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {metrics.map((metric) => (
          <MetricCard key={metric.id} data={metric} onSync={onSync} />
        ))}
      </div>
    </section>
  );
}

export const SOURCE_ICONS = {
  jira: <FileText className="w-6 h-6" />,
  confluence: <FileText className="w-6 h-6" />,
  github: <Code2 className="w-6 h-6" />,
  slack: <Hash className="w-6 h-6" />,
  meetings: <Video className="w-6 h-6" />,
};

export const SOURCE_ENTITY_LABELS: Record<keyof typeof SOURCE_ICONS, string> = {
  jira: "Issues",
  confluence: "Pages",
  github: "Items",
  slack: "Messages",
  meetings: "Transcripts",
};

export const SOURCE_COLORS = {
  jira: "#0052CC",
  confluence: "#172B4D",
  github: "#24292e",
  slack: "#4A154B",
  meetings: "#EA4335",
};
