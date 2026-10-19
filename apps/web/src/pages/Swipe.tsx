import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChoiceDeck } from "../components/ChoiceCard";
import { SourceBadge } from "../components/SourceBadge";
import { useSession } from "../stores/session";

const MAX_ROUNDS = 5;

export function Swipe() {
  const { view, answer, undo, reset, loading, notice, dismissNotice } = useSession();
  const q = view?.question;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!q || loading) return;
      if (e.key === "ArrowLeft") answer("L");
      else if (e.key === "ArrowRight") answer("R");
      else if (e.key === "Escape") answer("SKIP");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [q, loading, answer]);

  if (!q || !view) return null;

  const round = Math.min(q.revision, MAX_ROUNDS);

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[560px] flex-col px-5 pb-8 pt-6">
      <div className="flex items-center justify-between">
        <button
          onClick={reset}
          className="rounded-full border border-mcd-line bg-white px-3 py-1.5 text-xs text-mcd-mute"
        >
          ← 重来
        </button>
        <SourceBadge source={view.data_source} compact />
      </div>

      {/* 进度 */}
      <div className="mt-5 flex items-center gap-1.5">
        {Array.from({ length: MAX_ROUNDS }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < round ? "bg-mcd-red" : "bg-mcd-line"
            }`}
          />
        ))}
        <span className="ml-2 w-10 text-right text-[11px] tabular-nums text-mcd-mute">
          {round}/{MAX_ROUNDS}
        </span>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={q.id}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.22 }}
          className="mt-7"
        >
          <h2 className="text-[26px] font-black leading-snug text-mcd-dark">{q.prompt}</h2>
          {q.why && <p className="mt-2 text-[12.5px] leading-relaxed text-mcd-mute">{q.why}</p>}
        </motion.div>
      </AnimatePresence>

      <div className="mt-7">
        <ChoiceDeck question={q} onChoose={(c) => answer(c)} disabled={loading} />
      </div>

      <p className="mt-4 text-center text-[11.5px] text-mcd-mute">
        左右拖动整块卡片，或直接点选 · 键盘 ← → 也行
      </p>

      {notice && (
        <button
          onClick={dismissNotice}
          className="mt-4 w-full rounded-2xl bg-mcd-cream px-4 py-2.5 text-left text-[12.5px] leading-relaxed text-mcd-ink"
        >
          {notice}
        </button>
      )}

      <div className="safe-bottom mt-auto flex items-center gap-3 pt-8">
        <button
          onClick={undo}
          disabled={loading}
          className="flex-1 rounded-2xl border border-mcd-line bg-white py-3 text-[14px] font-medium text-mcd-ink disabled:opacity-50"
        >
          ↺ 撤销
        </button>
        <button
          onClick={() => answer("SKIP")}
          disabled={loading}
          className="flex-1 rounded-2xl border border-mcd-line bg-white py-3 text-[14px] font-medium text-mcd-mute disabled:opacity-50"
        >
          都不太对
        </button>
      </div>
    </div>
  );
}
