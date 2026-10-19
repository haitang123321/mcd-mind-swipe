import type { SessionView } from "../types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("连不上本地服务，请确认后端已启动（端口 8000）", 0);
  }
  if (!resp.ok) {
    let detail = `请求失败（${resp.status}）`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* 忽略解析失败 */
    }
    throw new ApiError(detail, resp.status);
  }
  return (await resp.json()) as T;
}

export const api = {
  start(input: string, mode: "auto" | "explore" | "fast" = "auto") {
    return request<SessionView>("/session/start", {
      method: "POST",
      body: JSON.stringify({ input, mode, consent: false }),
    });
  },

  answer(sessionId: string, questionId: string, choice: "L" | "R" | "SKIP", revision: number) {
    return request<SessionView>(`/session/${sessionId}/answer`, {
      method: "POST",
      body: JSON.stringify({
        question_id: questionId,
        choice,
        revision,
        request_id: uid(),
      }),
    });
  },

  undo(sessionId: string) {
    return request<SessionView>(`/session/${sessionId}/undo`, {
      method: "POST",
      body: JSON.stringify({ request_id: uid() }),
    });
  },

  feedback(sessionId: string, mealCode: string, action: string, scope: "session" | "long_term" = "session") {
    return request<{ updated: boolean; stage: string; notice: string }>(
      `/session/${sessionId}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({ meal_code: mealCode, action, scope, request_id: uid() }),
      },
    );
  },

  health() {
    return request<Record<string, unknown>>("/health");
  },
};

function uid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
