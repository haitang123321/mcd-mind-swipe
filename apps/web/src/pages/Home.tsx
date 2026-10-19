import { useState } from "react";
import { motion } from "framer-motion";
import { useSession } from "../stores/session";

const QUICK = [
  "今天吃什么",
  "加班了，想吃点好的",
  "30 元以内，不想太油",
  "想吃点辣的",
  "早餐，来点热的",
  "来杯咖啡提神",
];

export function Home() {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"explore" | "fast">("explore");
  const { start, loading, error } = useSession();

  const submit = () => {
    if (loading) return;
    void start(text.trim(), mode);
  };

  return (
    <div className="paper relative mx-auto flex min-h-full w-full max-w-[560px] flex-col px-5 pb-8 pt-10">
      {/* 背景色块 */}
      <div className="pointer-events-none absolute -right-16 top-10 h-56 w-56 rounded-full bg-mcd-yellow/25 blur-3xl" />
      <div className="pointer-events-none absolute -left-20 top-52 h-48 w-48 rounded-full bg-mcd-red/10 blur-3xl" />

      <header className="relative">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-mcd-line bg-white/70 px-3 py-1 text-[11px] text-mcd-mute backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-mcd-red" />
          独立第三方创意项目 · 非麦当劳官方出品
        </div>

        <h1 className="text-[40px] font-black leading-[1.05] tracking-tight text-mcd-dark">
          麦麦
          <span className="text-mcd-red">读心术</span>
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-mcd-mute">
          你不用填问卷。说一句想吃什么样，
          <br />
          我来问，你来选，越选越懂你。
        </p>
      </header>

      <main className="relative mt-8 flex-1">
        <div className="rounded-blob border border-mcd-line bg-white p-4 shadow-card">
          <label className="sr-only" htmlFor="wish">
            描述你今天想吃什么
          </label>
          <textarea
            id="wish"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={3}
            maxLength={300}
            placeholder="比如：今天加班了，预算 35，不想吃太油"
            className="w-full resize-none bg-transparent text-[16px] leading-relaxed text-mcd-ink outline-none placeholder:text-mcd-mute/60"
          />
          <div className="mt-2 flex items-center justify-between border-t border-mcd-line pt-3">
            <div className="flex items-center gap-1 rounded-full bg-mcd-cream p-0.5">
              {(
                [
                  ["explore", "慢慢聊"],
                  ["fast", "直接给"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setMode(key)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    mode === key ? "bg-white text-mcd-red shadow-sm" : "text-mcd-mute"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-mcd-mute">{text.length}/300</span>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {QUICK.map((q) => (
            <button
              key={q}
              onClick={() => setText(q)}
              className="rounded-full border border-mcd-line bg-white/80 px-3 py-1.5 text-[13px] text-mcd-ink transition hover:border-mcd-red/40 hover:text-mcd-red"
            >
              {q}
            </button>
          ))}
        </div>

        {error && (
          <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-[13px] leading-relaxed text-red-700">
            {error}
          </p>
        )}
      </main>

      <footer className="safe-bottom relative mt-8">
        <motion.button
          whileTap={{ scale: 0.98 }}
          onClick={submit}
          disabled={loading}
          className="w-full rounded-2xl bg-mcd-red py-4 text-[16px] font-bold text-white shadow-lift transition disabled:opacity-70"
        >
          {loading ? "正在读你的心…" : "开始，别让我猜太久"}
        </motion.button>
        <p className="mt-3 text-center text-[11px] leading-relaxed text-mcd-mute">
          推荐基于菜单与你的选择生成，不构成营养或医疗建议。
          <br />
          餐品价格与供应以门店实时结果为准。
        </p>
      </footer>
    </div>
  );
}
