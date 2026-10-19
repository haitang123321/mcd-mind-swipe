import { motion, useMotionValue, useTransform, type MotionValue } from "framer-motion";
import type { ChoiceOption, Question } from "../types";

const ICONS: Record<string, string> = {
  high_satiety: "🍔",
  light_meal: "🥗",
  value_first: "💰",
  treat_self: "🎉",
  spicy: "🌶️",
  mild: "🍦",
  savory: "🍟",
  sweet_tooth: "🍰",
  classic: "⭐",
  novelty: "✨",
};

const TONE = {
  L: {
    card: "from-[#FFF3DF] via-[#FFE7C2] to-[#FFD79B]",
    ring: "ring-[#E8A33D]",
    ink: "text-[#7A3E00]",
    sub: "text-[#A9691F]",
    badge: "bg-[#7A3E00]/10",
  },
  R: {
    card: "from-[#EAF7E9] via-[#D8F0D6] to-[#BFE5BC]",
    ring: "ring-[#4E9A4A]",
    ink: "text-[#1E4D20]",
    sub: "text-[#3F7A3C]",
    badge: "bg-[#1E4D20]/10",
  },
};

export function ChoiceDeck({
  question,
  onChoose,
  disabled,
}: {
  question: Question;
  onChoose: (choice: "L" | "R") => void;
  disabled?: boolean;
}) {
  const x = useMotionValue(0);
  const leftScale = useTransform(x, [-170, 0], [1.05, 1]);
  const rightScale = useTransform(x, [0, 170], [1, 1.05]);
  const leftShadow = useTransform(x, [-170, 0], ["0 24px 44px -16px rgba(122,62,0,0.35)", "0 0 0 rgba(0,0,0,0)"]);
  const rightShadow = useTransform(x, [0, 170], ["0 0 0 rgba(0,0,0,0)", "0 24px 44px -16px rgba(30,77,32,0.32)"]);

  return (
    <motion.div
      drag={disabled ? false : "x"}
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.22}
      style={{ x }}
      onDragEnd={(_, info) => {
        if (disabled) return;
        if (info.offset.x < -70) onChoose("L");
        else if (info.offset.x > 70) onChoose("R");
      }}
      className="flex w-full gap-3"
    >
      <OptionCard
        option={question.left}
        tone="L"
        scale={leftScale}
        shadow={leftShadow}
        onPick={() => !disabled && onChoose("L")}
      />
      <OptionCard
        option={question.right}
        tone="R"
        scale={rightScale}
        shadow={rightShadow}
        onPick={() => !disabled && onChoose("R")}
      />
    </motion.div>
  );
}

function OptionCard({
  option,
  tone,
  scale,
  shadow,
  onPick,
}: {
  option: ChoiceOption;
  tone: "L" | "R";
  scale: MotionValue<number>;
  shadow: MotionValue<string>;
  onPick: () => void;
}) {
  const t = TONE[tone];
  return (
    <motion.button
      type="button"
      style={{ scale, boxShadow: shadow }}
      whileTap={{ scale: 0.98 }}
      onClick={onPick}
      className={`relative flex-1 overflow-hidden rounded-blob bg-gradient-to-b ${t.card} p-5 text-left ring-1 ring-inset ring-white/60`}
    >
      <span className={`absolute right-3 top-3 rounded-full px-2 py-0.5 text-[10px] font-medium ${t.badge} ${t.sub}`}>
        {tone === "L" ? "左" : "右"}
      </span>
      <div className="text-[40px] leading-none">{ICONS[option.attribute] ?? "🍔"}</div>
      <div className={`mt-4 text-[19px] font-bold leading-tight ${t.ink}`}>{option.label}</div>
      {option.description && (
        <p className={`mt-1 text-[12px] leading-relaxed ${t.sub}`}>{option.description}</p>
      )}
    </motion.button>
  );
}
