/** 与后端 Pydantic 契约一一对应（services/api/app/models/schemas.py）。 */

export type Stage =
  | "created"
  | "understanding"
  | "questioning"
  | "recommending"
  | "accepted"
  | "ended";

export interface Nutrition {
  energy_kcal: number;
  protein: number;
  fat: number;
  carbohydrate: number;
  sodium: number;
  calcium: number;
}

export interface ChoiceOption {
  id: "L" | "R";
  label: string;
  attribute: string;
  description?: string | null;
}

export interface Question {
  id: string;
  dimension: string;
  prompt: string;
  left: ChoiceOption;
  right: ChoiceOption;
  allow_skip: boolean;
  revision: number;
  value_score: number;
  why?: string | null;
}

export interface Recommendation {
  rank: number;
  code: string;
  name: string;
  price: number;
  category: string;
  score: number;
  reason: string;
  nutrition: Nutrition;
  tags: string[];
  confidence: "low" | "medium" | "high";
}

export interface ParsedContext {
  budget: number | null;
  satiety_pref: number | null;
  accept_spicy: boolean | null;
  want_spicy: boolean;
  exclude_oily: boolean;
  caffeine_need: boolean;
  categories: string[];
  mains_exclude: string[];
  mains_include: string[];
  meal_period: string | null;
  mood: string | null;
  keywords: string[];
  confidence: number;
  evidence: string[];
}

export interface DataSource {
  type: "mock" | "mcp" | "cache";
  label: string;
  store_id: string | null;
  store_name: string | null;
  fetched_at: string | null;
  price_notice: string;
}

export interface DebugInfo {
  candidates: number;
  questions_asked: number;
  engine_ms: number;
  llm_used: boolean;
  llm_tokens: number;
  top_score: number;
  second_score: number;
  stop_reason: string | null;
}

export interface SessionView {
  session_id: string;
  stage: Stage;
  parsed: ParsedContext;
  question: Question | null;
  recommendations: Recommendation[];
  data_source: DataSource;
  debug: DebugInfo;
  revision: number;
  duplicate: boolean;
  notice: string | null;
}
