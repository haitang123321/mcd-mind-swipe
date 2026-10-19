import { create } from "zustand";
import { ApiError, api } from "../api/client";
import type { SessionView } from "../types";

export type Screen = "home" | "swiping" | "results";

interface SessionStore {
  screen: Screen;
  view: SessionView | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  /** 每次成功请求后的快照，用于本地撤销时立刻回退 UI */
  trail: SessionView[];

  start: (input: string, mode?: "auto" | "explore" | "fast") => Promise<void>;
  answer: (choice: "L" | "R" | "SKIP") => Promise<void>;
  undo: () => Promise<void>;
  feedback: (mealCode: string, action: string) => Promise<void>;
  reset: () => void;
  dismissNotice: () => void;
}

function screenOf(view: SessionView): Screen {
  if (view.question) return "swiping";
  if (view.recommendations.length > 0 || view.stage === "recommending") return "results";
  return "swiping";
}

export const useSession = create<SessionStore>((set, get) => ({
  screen: "home",
  view: null,
  loading: false,
  error: null,
  notice: null,
  trail: [],

  async start(input, mode = "auto") {
    set({ loading: true, error: null, notice: null });
    try {
      const view = await api.start(input, mode);
      set({
        view,
        screen: screenOf(view),
        loading: false,
        trail: [view],
        notice: view.notice ?? null,
      });
    } catch (err) {
      set({ loading: false, error: err instanceof ApiError ? err.message : "出错了，请重试" });
    }
  },

  async answer(choice) {
    const { view, trail } = get();
    if (!view?.question) return;
    set({ loading: true, error: null });
    // 乐观交互：先把卡片状态交出去，动画不受网络影响
    try {
      const next = await api.answer(view.session_id, view.question.id, choice, view.revision);
      set({
        view: next,
        screen: screenOf(next),
        loading: false,
        trail: [...trail, next].slice(-8),
        notice: next.notice ?? null,
      });
    } catch (err) {
      set({ loading: false, error: err instanceof ApiError ? err.message : "选择没有提交成功" });
    }
  },

  async undo() {
    const { view, trail } = get();
    if (!view) return;
    set({ loading: true, error: null });
    try {
      const prev = trail.length >= 2 ? trail[trail.length - 2] : null;
      const next = await api.undo(view.session_id);
      set({
        view: next,
        screen: screenOf(next),
        loading: false,
        trail: prev ? trail.slice(0, -1) : trail,
        notice: next.notice ?? null,
      });
    } catch (err) {
      set({ loading: false, error: err instanceof ApiError ? err.message : "撤销失败" });
    }
  },

  async feedback(mealCode, action) {
    const { view } = get();
    if (!view) return;
    try {
      const res = await api.feedback(view.session_id, mealCode, action);
      set({ notice: res.notice });
    } catch {
      /* 反馈失败不打断主流程 */
    }
  },

  reset() {
    set({ screen: "home", view: null, loading: false, error: null, notice: null, trail: [] });
  },

  dismissNotice() {
    set({ notice: null, error: null });
  },
}));
