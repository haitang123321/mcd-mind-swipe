import type { DataSource } from "../types";

const STYLES: Record<string, { bg: string; text: string; dot: string; prefix: string }> = {
  mock: { bg: "bg-amber-50", text: "text-amber-800", dot: "bg-amber-400", prefix: "示例" },
  mcp: { bg: "bg-emerald-50", text: "text-emerald-800", dot: "bg-emerald-500", prefix: "实时" },
  cache: { bg: "bg-sky-50", text: "text-sky-800", dot: "bg-sky-500", prefix: "缓存" },
};

export function SourceBadge({ source, compact = false }: { source: DataSource; compact?: boolean }) {
  const s = STYLES[source.type] ?? STYLES.mock;
  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full ${s.bg} ${s.text} ${
        compact ? "px-2 py-0.5 text-[11px]" : "px-3 py-1 text-xs"
      } font-medium`}
      title={source.price_notice}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      <span>
        {source.label}
        {source.store_name && !compact ? ` · ${source.store_name}` : ""}
      </span>
    </div>
  );
}
