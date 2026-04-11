import React from "react";

type FeatureScores = {
  structure?: number;
  trend_alignment?: number;
  momentum?: number;
  reclaim_or_breakout?: number;
  volume?: number;
  risk_reward?: number;
  regime_fit?: number;
  trend_maturity_penalty?: number;
};

type StrategyEvaluation = {
  valid?: boolean;
  base_score?: number;
  bias?: number;
  final_score?: number;
  reason?: string | null;
  feature_scores?: FeatureScores;
};

export type StrategyDiagnosticCardData = {
  strategyKey: string;
  strategyLabel: string;
  confidence: number;
  regime?: string | null;
  evaluation?: StrategyEvaluation;
  selected?: boolean;
};

const FEATURE_META: Array<{
  key: keyof FeatureScores;
  label: string;
  negative?: boolean;
}> = [
  { key: "structure", label: "Structure" },
  { key: "trend_alignment", label: "Trend align" },
  { key: "momentum", label: "Momentum" },
  { key: "reclaim_or_breakout", label: "Reclaim / breakout" },
  { key: "volume", label: "Volume" },
  { key: "risk_reward", label: "Risk / reward" },
  { key: "regime_fit", label: "Regime fit" },
  { key: "trend_maturity_penalty", label: "Maturity penalty", negative: true },
];

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v));
}

function pct(v?: number) {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  return `${Math.round(clamp01(v) * 100)}%`;
}

function num(v?: number) {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  return v.toFixed(3);
}

function labelFromKey(key: string): string {
  const map: Record<string, string> = {
    pullback_reclaim: "Pullback Reclaim",
    trend_continuation: "Momentum Breakout Continuation",
    mean_reversion_bounce: "Mean Reversion Bounce",
    range_rotation: "Range Rotation Reversal",
    breakout_retest: "Breakout Retest Hold",
  };
  return map[key] ?? key.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildSummary(data: StrategyDiagnosticCardData): string {
  const fs = data.evaluation?.feature_scores ?? {};
  const parts: string[] = [];

  if ((fs.trend_alignment ?? 0) >= 0.75) parts.push("strong trend alignment");
  if ((fs.structure ?? 0) >= 0.75) parts.push("clean structure");
  if ((fs.momentum ?? 0) >= 0.65) parts.push("strong momentum");
  if ((fs.reclaim_or_breakout ?? 0) >= 0.65) parts.push("good trigger quality");
  if ((fs.regime_fit ?? 0) >= 0.75) parts.push("high regime fit");
  if ((fs.trend_maturity_penalty ?? 0) >= 0.25) parts.push("maturity penalty applied");

  if (parts.length === 0) return "Mixed signal profile";
  return parts.join(" • ");
}

function FeatureBar({
  label,
  value,
  negative = false,
}: {
  label: string;
  value?: number;
  negative?: boolean;
}) {
  const normalized = typeof value === "number" ? clamp01(value) : 0;
  const width = `${Math.round(normalized * 100)}%`;

  return (
    <div className="grid grid-cols-[120px_1fr_44px] items-center gap-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/65">
        {label}
      </div>
      <div className="h-2 rounded-full bg-slate-900/90 ring-1 ring-cyan-400/10 overflow-hidden">
        <div
          className={[
            "h-full rounded-full transition-all",
            negative ? "bg-red-400/80" : "bg-cyan-400/80",
          ].join(" ")}
          style={{ width }}
        />
      </div>
      <div className="text-right text-[11px] font-mono text-cyan-100/80">
        {num(value)}
      </div>
    </div>
  );
}

export default function StrategyDiagnosticCard({
  strategyKey,
  strategyLabel,
  confidence,
  regime,
  evaluation,
  selected = false,
}: StrategyDiagnosticCardData) {
  const fs = evaluation?.feature_scores ?? {};
  const resolvedLabel = strategyLabel || labelFromKey(strategyKey);
  const summary = buildSummary({
    strategyKey,
    strategyLabel: resolvedLabel,
    confidence,
    regime,
    evaluation,
    selected,
  });

  return (
    <div
      className={[
        "rounded-2xl border bg-slate-950/95 p-5 shadow-[0_0_0_1px_rgba(34,211,238,0.06)]",
        selected
          ? "border-cyan-400/40 shadow-[0_0_24px_rgba(34,211,238,0.10)]"
          : "border-cyan-400/15",
      ].join(" ")}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-cyan-300">⚡</span>
            <h3 className="text-base font-semibold uppercase tracking-[0.18em] text-slate-100">
              {resolvedLabel}
            </h3>
          </div>
          <div className="mt-2 text-[11px] uppercase tracking-[0.2em] text-cyan-100/55">
            {regime || "unknown"}
          </div>
        </div>

        <div className="rounded-md border border-cyan-400/20 bg-cyan-400/8 px-3 py-1 text-sm font-semibold text-cyan-300">
          {pct(confidence)}
        </div>
      </div>

      <div className="space-y-3">
        {FEATURE_META.map((item) => (
          <FeatureBar
            key={item.key}
            label={item.label}
            value={fs[item.key]}
            negative={item.negative}
          />
        ))}
      </div>

      <div className="mt-5 grid grid-cols-3 gap-3 border-t border-cyan-400/10 pt-4">
        <div className="rounded-lg bg-slate-900/70 p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">
            Base
          </div>
          <div className="mt-1 font-mono text-sm text-slate-100">
            {num(evaluation?.base_score)}
          </div>
        </div>
        <div className="rounded-lg bg-slate-900/70 p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">
            Bias
          </div>
          <div className="mt-1 font-mono text-sm text-slate-100">
            {num(evaluation?.bias)}
          </div>
        </div>
        <div className="rounded-lg bg-slate-900/70 p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">
            Final
          </div>
          <div className="mt-1 font-mono text-sm text-slate-100">
            {num(evaluation?.final_score)}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-cyan-400/10 bg-slate-900/50 p-3">
        <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-100/55">
          Why this ranked here
        </div>
        <div className="mt-2 text-sm text-slate-200/90">{summary}</div>
        {evaluation?.reason ? (
          <div className="mt-2 text-xs text-amber-300/85">
            Reason: {evaluation.reason}
          </div>
        ) : null}
      </div>
    </div>
  );
}