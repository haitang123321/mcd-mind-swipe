import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { SourceBadge } from "../components/SourceBadge";
import { useSession } from "../stores/session";
import type { Recommendation } from "../types";

const CONF_LABEL: Record<string, string> = { high: "很笃定", medium: "比较稳", low: "还在猜" };

export function Results() {
  const { view, reset, feedback, notice, dismissNotice } = useSession();
  const [index, setIndex] = useState(0);
  const [accepted, setAccepted] = useState<string | null>(null);

  useEffect(() => {
    setIndex(0);
    setAccepted(null);
  }, [view?.session_id]);

  if (!view) return null;
  const list = view.recommendations;

  if (list.length === 0) {
    return (
      <div className="mx-auto flex min-h-full w-full max-w-[560px] flex-col px-5 pb-8 pt-16">
        <h2 className="text-[24px] font-black leading-snug text-mcd-dark">这次真没有合适的</h2>
        <p className="mt-3 text-[14px] leading-relaxed text-mcd-mute">
          {view.notice ?? "没有符合当前条件的在售餐品，可以放宽预算或取消忌口再试一次。"}
        </p>
        <button
          onClick={reset}
          className="mt-8 w-full rounded-2xl bg-mcd-red py-4 text-[15px] font-bold text-white"
        >
          重新说一次
        </button>
      </div>
    );
  }

  const hero = list[Math.min(index, list.length - 1)];

  const swap = () => {
    if (list.length <= 1) return;
    setIndex((i) => (i + 1) % list.length);
  };

  const accept = (item: Recommendation) => {
    setAccepted(item.code);
    void feedback(item.code, "accept");
  };

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

      <div className="mt-6">
        <h2 className="text-[28px] font-black leading-tight text-mcd-dark">猜你想吃这个</h2>
        <p className="mt-1.5 text-[13px] text-mcd-mute">
          问了 {view.debug.questions_asked} 轮，从 {view.debug.candidates} 个在售餐品里挑出来
        </p>
      </div>

      <div className="mt-5">
        <AnimatePresence mode="wait">
          <motion.div
            key={hero.code}
            drag="x"
            dragConstraints={{ left: 0, right: 0 }}
            dragElastic={0.25}
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.22 }}
            onDragEnd={(_, info) => {
              if (info.offset.x < -80) swap();
              else if (info.offset.x > 80) accept(hero);
            }}
            className="rounded-blob border border-mcd-line bg-white p-6 shadow-card"
          >
            <div className="flex items-start justify-between">
              <span className="rounded-full bg-mcd-red px-2.5 py-1 text-[11px] font-bold text-white">
                第 {index + 1} 名
              </span>
              <span className="text-[11px] text-mcd-mute">{CONF_LABEL[hero.confidence]}</span>
            </div>

            <h3 className="mt-4 text-[24px] font-black leading-snug text-mcd-dark">{hero.name}</h3>

            <div className="mt-3 flex items-baseline gap-1.5">
              <span className="text-[13px] text-mcd-mute">¥</span>
              <span className="text-[30px] font-black tabular-nums text-mcd-red">
                {hero.price.toFixed(hero.price % 1 === 0 ? 0 : 1)}
              </span>
              <span className="ml-1 text-[11px] text-mcd-mute">门店标价</span>
            </div>

            <p className="mt-4 rounded-2xl bg-mcd-cream px-4 py-3 text-[13px] leading-relaxed text-mcd-ink">
              {hero.reason}
            </p>

            <div className="mt-4 flex flex-wrap gap-1.5">
              {hero.tags.filter(Boolean).map((t) => (
                <span key={t} className="rounded-full bg-mcd-cream px-2.5 py-1 text-[11px] text-mcd-mute">
                  {t}
                </span>
              ))}
            </div>

            {hero.nutrition.energy_kcal > 0 && (
              <div className="mt-4 grid grid-cols-3 gap-2 border-t border-mcd-line pt-4 text-center">
                <Metric k="热量" v={`${Math.round(hero.nutrition.energy_kcal)} kcal`} />
                <Metric k="蛋白" v={`${hero.nutrition.protein} g`} />
                <Metric k="脂肪" v={`${hero.nutrition.fat} g`} />
                <span className="col-span-3 text-[10px] text-mcd-mute">营养数据来自公开餐品营养表</span>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        {accepted === hero.code ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-center text-[13px] font-medium text-emerald-800"
          >
            记下了：今天就吃「{hero.name}」。下次我会更准一点。
          </motion.div>
        ) : (
          <div className="mt-4 flex gap-3">
            <button
              onClick={swap}
              disabled={list.length <= 1}
              className="flex-1 rounded-2xl border border-mcd-line bg-white py-3.5 text-[14px] font-medium text-mcd-ink disabled:opacity-40"
            >
              换一个
            </button>
            <button
              onClick={() => accept(hero)}
              className="flex-1 rounded-2xl bg-mcd-red py-3.5 text-[14px] font-bold text-white"
            >
              就它了
            </button>
          </div>
        )}
      </div>

      {list.length > 1 && (
        <div className="mt-7">
          <div className="mb-2 text-[12px] font-medium text-mcd-mute">另外两个备选</div>
          <div className="space-y-2">
            {list.map((item, i) =>
              i === index ? null : (
                <button
                  key={item.code}
                  onClick={() => setIndex(i)}
                  className="flex w-full items-center justify-between rounded-2xl border border-mcd-line bg-white/80 px-4 py-3 text-left transition hover:border-mcd-red/30"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[14px] font-medium text-mcd-ink">{item.name}</span>
                    <span className="mt-0.5 block truncate text-[11.5px] text-mcd-mute">{item.reason}</span>
                  </span>
                  <span className="ml-3 shrink-0 text-[14px] font-bold tabular-nums text-mcd-red">
                    ¥{item.price.toFixed(item.price % 1 === 0 ? 0 : 1)}
                  </span>
                </button>
              ),
            )}
          </div>
        </div>
      )}

      {notice && (
        <button
          onClick={dismissNotice}
          className="mt-5 w-full rounded-2xl bg-mcd-cream px-4 py-2.5 text-left text-[12px] leading-relaxed text-mcd-ink"
        >
          {notice}
        </button>
      )}

      <div className="safe-bottom mt-auto pt-8">
        <button
          onClick={reset}
          className="w-full rounded-2xl border border-mcd-line bg-white py-3.5 text-[14px] font-medium text-mcd-mute"
        >
          重新开始
        </button>
        <p className="mt-3 text-center text-[10.5px] leading-relaxed text-mcd-mute">
          {view.data_source.price_notice}
          <br />
          本工具只做推荐，不创建订单、不代付。
        </p>
      </div>
    </div>
  );
}

function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10px] text-mcd-mute">{k}</div>
      <div className="text-[13px] font-semibold text-mcd-ink">{v}</div>
    </div>
  );
}
