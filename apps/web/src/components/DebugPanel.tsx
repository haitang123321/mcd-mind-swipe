import { useState } from "react";
import type { DebugInfo, ParsedContext } from "../types";

/** 演示面板（P5）：只展示聚合指标，不暴露 Token、密钥或个人信息。 */
export function DebugPanel({ debug, parsed }: { debug: DebugInfo; parsed: ParsedContext }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-3 left-3 z-40 text-[11px]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded-full border border-mcd-line bg-white/90 px-2.5 py-1 text-mcd-mute shadow-sm backdrop-blur"
      >
        {open ? "收起调试" : "调试"}
      </button>
      {open && (
        <div className="mt-2 w-64 rounded-2xl border border-mcd-line bg-white/95 p-3 shadow-card backdrop-blur">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-semibold text-mcd-ink">决策面板</span>
            <span className="text-mcd-mute">{debug.engine_ms} ms</span>
          </div>
          <Row k="候选数" v={String(debug.candidates)} />
          <Row k="已问" v={`${debug.questions_asked} 轮`} />
          <Row k="首位得分" v={debug.top_score.toFixed(3)} />
          <Row k="次位得分" v={debug.second_score.toFixed(3)} />
          <Row k="停止原因" v={debug.stop_reason ?? "—"} />
          <Row k="LLM" v={debug.llm_used ? `已用 ${debug.llm_tokens} tokens` : "未启用（规则引擎）"} />
          <div className="mt-2 border-t border-mcd-line pt-2">
            <div className="mb-1 text-mcd-mute">意图解析</div>
            <Row k="预算" v={parsed.budget != null ? `¥${parsed.budget}` : "未指定"} />
            <Row k="口味" v={parsed.satiety_pref != null ? (parsed.satiety_pref > 0 ? "偏饱腹" : "偏清爽") : "未指定"} />
            <Row k="置信度" v={parsed.confidence.toFixed(2)} />
            {parsed.evidence.length > 0 && (
              <p className="mt-1 leading-relaxed text-mcd-mute">证据：{parsed.evidence.join("、")}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-mcd-mute">{k}</span>
      <span className="font-mono text-mcd-ink">{v}</span>
    </div>
  );
}
