import { DebugPanel } from "./components/DebugPanel";
import { Home } from "./pages/Home";
import { Results } from "./pages/Results";
import { Swipe } from "./pages/Swipe";
import { useSession } from "./stores/session";

export default function App() {
  const { screen, view, error, dismissNotice } = useSession();

  return (
    <div className="relative min-h-full">
      {/*
        刻意不用 AnimatePresence 的 exit 动画：页面切换时若退场动画未回调，
        新页面会停在 opacity:0 上（实测白屏）。改用 key 重挂 + CSS 入场，稳定优先。
      */}
      <div key={screen} className="min-h-full fade-up">
        {screen === "home" && <Home />}
        {screen === "swiping" && <Swipe />}
        {screen === "results" && <Results />}
      </div>

      {error && screen !== "home" && (
        <button
          onClick={dismissNotice}
          className="fixed left-1/2 top-4 z-50 w-[calc(100%-2.5rem)] max-w-[520px] -translate-x-1/2 rounded-2xl bg-red-600 px-4 py-3 text-left text-[12.5px] leading-relaxed text-white shadow-card"
        >
          {error}（点此关闭）
        </button>
      )}

      {view && screen !== "home" && <DebugPanel debug={view.debug} parsed={view.parsed} />}
    </div>
  );
}
