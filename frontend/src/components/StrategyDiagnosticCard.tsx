import React from "react"

type FeatureScores = {
  structure?: number
  trend_alignment?: number
  momentum?: number
  reclaim_or_breakout?: number
  volume?: number
  risk_reward?: number
  regime_fit?: number
  trend_maturity_penalty?: number
}

type StrategyEvaluation = {
  valid?: boolean
  base_score?: number
  bias?: number
  final_score?: number
  reason?: string | null
  feature_scores?: FeatureScores
}

type Props = {
  strategyKey: string
  label: string
  confidence: number
  regime?: string
  evaluation?: StrategyEvaluation
  selected?: boolean
}

const FEATURES: Array<{
  key: keyof FeatureScores
  label: string
  negative?: boolean
}> = [
  { key: "structure", label: "Structure" },
  { key: "trend_alignment", label: "Trend" },
  { key: "momentum", label: "Momentum" },
  { key: "reclaim_or_breakout", label: "Trigger" },
  { key: "volume", label: "Volume" },
  { key: "risk_reward", label: "RR" },
  { key: "regime_fit", label: "Regime fit" },
  { key: "trend_maturity_penalty", label: "Maturity", negative: true }
]

function pct(v?: number) {
  if (typeof v !== "number") return "—"
  return `${Math.round(v * 100)}%`
}

function bar(v?: number) {
  if (typeof v !== "number") return "0%"
  return `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`
}

function summary(fs: FeatureScores = {}) {
  const notes: string[] = []

  if ((fs.structure ?? 0) > 0.75) notes.push("clean structure")
  if ((fs.trend_alignment ?? 0) > 0.75) notes.push("trend aligned")
  if ((fs.momentum ?? 0) > 0.65) notes.push("momentum present")
  if ((fs.reclaim_or_breakout ?? 0) > 0.65) notes.push("strong trigger")
  if ((fs.regime_fit ?? 0) > 0.75) notes.push("regime supportive")
  if ((fs.trend_maturity_penalty ?? 0) > 0.25) notes.push("late trend")

  if (!notes.length) return "mixed profile"

  return notes.join(" • ")
}

export default function StrategyCard({
  strategyKey,
  label,
  confidence,
  regime,
  evaluation,
  selected
}: Props) {

  const fs = evaluation?.feature_scores ?? {}

  return (
    <div
      className={`
        rounded-xl
        border
        p-4
        bg-slate-950
        ${selected
          ? "border-cyan-400 shadow-[0_0_20px_rgba(34,211,238,0.15)]"
          : "border-slate-800"}
      `}
    >

      {/* header */}

      <div className="flex justify-between items-start mb-3">

        <div>

          <div className="text-xs tracking-widest text-cyan-300">
            {label}
          </div>

          <div className="text-[10px] text-slate-400 mt-1">
            {regime}
          </div>

        </div>

        <div className="text-cyan-300 text-sm font-semibold">
          {pct(confidence)}
        </div>

      </div>

      {/* feature bars */}

      <div className="space-y-2">

        {FEATURES.map(f => {

          const val = fs[f.key]

          return (

            <div
              key={f.key}
              className="grid grid-cols-[90px_1fr_40px] gap-2 items-center"
            >

              <div className="text-[10px] text-slate-400">
                {f.label}
              </div>

              <div className="h-1.5 bg-slate-800 rounded">

                <div
                  className={`
                    h-full
                    rounded
                    ${f.negative
                      ? "bg-red-400"
                      : "bg-cyan-400"}
                  `}
                  style={{ width: bar(val) }}
                />

              </div>

              <div className="text-[10px] text-slate-300 font-mono text-right">
                {val?.toFixed(2) ?? "—"}
              </div>

            </div>

          )

        })}

      </div>

      {/* score summary */}

      <div className="mt-4 pt-3 border-t border-slate-800">

        <div className="grid grid-cols-3 gap-2 text-[10px]">

          <div>
            <div className="text-slate-500">base</div>
            <div className="text-slate-200 font-mono">
              {evaluation?.base_score?.toFixed(3)}
            </div>
          </div>

          <div>
            <div className="text-slate-500">bias</div>
            <div className="text-slate-200 font-mono">
              {evaluation?.bias?.toFixed(3)}
            </div>
          </div>

          <div>
            <div className="text-slate-500">final</div>
            <div className="text-cyan-300 font-mono">
              {evaluation?.final_score?.toFixed(3)}
            </div>
          </div>

        </div>

      </div>

      {/* explanation */}

      <div className="mt-3 text-[11px] text-slate-400">

        {summary(fs)}

      </div>

      {evaluation?.reason && (

        <div className="text-[10px] text-amber-400 mt-2">

          {evaluation.reason}

        </div>

      )}

    </div>
  )

}