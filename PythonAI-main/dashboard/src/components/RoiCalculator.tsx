"use client";

import { useEffect, useMemo, useState } from "react";
import { getCaptureStats, getTrainingStatus } from "@/lib/api";
import type { CaptureStats, TrainingRun } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import {
  DollarSign,
  Users,
  TrendingUp,
  Target,
  Zap,
  Calculator,
  Sliders,
  ChevronDown,
  ChevronUp,
  Brain,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────

interface RoiInputs {
  teamSize: number;
  avgSalary: number;
}

interface RoiResults {
  currentRate: number;
  projectedRate: number;
  productivityGainPct: number;
  annualValueTotal: number;
  forgeaiAnnualCost: number;
  netAnnualSavings: number;
  roiPercent: number;
  paybackDays: number;
  tier: string;
}

// ─── Pricing Tiers ──────────────────────────────────────────────

const PRICING_TIERS = [
  { maxDevs: 1, name: "Go", monthly: 9, annual: 9 * 12 },
  { maxDevs: 5, name: "Team", monthly: 49, annual: 49 * 12 },
  { maxDevs: 20, name: "Scale", monthly: 199, annual: 199 * 12 },
  { maxDevs: Infinity, name: "Enterprise", monthly: 3000, annual: 3000 * 12 },
] as const;

function getPricing(teamSize: number): { name: string; annual: number; monthly: number } {
  for (const tier of PRICING_TIERS) {
    if (teamSize <= tier.maxDevs) {
      return { name: tier.name, annual: tier.annual, monthly: tier.monthly };
    }
  }
  return { name: "Enterprise", annual: 36000, monthly: 3000 };
}

// ─── ROI Calculation ────────────────────────────────────────────

function computeRoi(
  inputs: RoiInputs,
  currentRate: number,
  avgTrainingDelta: number,
  trainingRunCount: number,
): RoiResults {
  const { teamSize, avgSalary } = inputs;

  // Projected rate: current + avg delta improvement from 12 more training runs (3 months)
  const projectedRuns = Math.max(1, 12 - trainingRunCount);
  const rateImprovement = Math.min(avgTrainingDelta * projectedRuns, 40); // Cap at +40pp (PRD target)
  const projectedRate = Math.min(currentRate + rateImprovement, 95); // Cap at 95%

  // Productivity gain: 0.75% per pp improvement (40pp → 30% gain per PRD)
  const productivityGainPct = Math.min(rateImprovement * 0.75, 35);

  // Annual value
  const annualValueTotal = teamSize * avgSalary * (productivityGainPct / 100);

  // ForgeAI cost
  const pricing = getPricing(teamSize);
  const forgeaiAnnualCost = pricing.annual;

  // Net savings
  const netAnnualSavings = annualValueTotal - forgeaiAnnualCost;

  // ROI percent
  const roiPercent = forgeaiAnnualCost > 0
    ? Math.round((netAnnualSavings / forgeaiAnnualCost) * 100)
    : 0;

  // Payback period (days)
  const dailyValue = annualValueTotal / 365;
  const paybackDays = dailyValue > 0
    ? Math.round(pricing.monthly / dailyValue)
    : 0;

  return {
    currentRate,
    projectedRate,
    productivityGainPct: Math.round(productivityGainPct * 10) / 10,
    annualValueTotal: Math.round(annualValueTotal),
    forgeaiAnnualCost,
    netAnnualSavings: Math.round(netAnnualSavings),
    roiPercent,
    paybackDays,
    tier: pricing.name,
  };
}

// ─── Format helpers ─────────────────────────────────────────────

function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${formatNumber(value)}`;
  return `$${value.toLocaleString()}`;
}

// ─── Sub-components ─────────────────────────────────────────────

function ValueDisplay({
  label,
  value,
  subtitle,
  trend,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  subtitle?: string;
  trend?: { direction: "up" | "down"; value: string };
  icon: React.ElementType;
  accent?: string;
}) {
  const accentClass = accent || "text-forge-primary";
  return (
    <div className="card p-4 hover:bg-forge-elevated/50 transition-colors group">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium">
          {label}
        </span>
        <Icon size={14} className={accentClass} />
      </div>
      <div className={cn("text-xl font-bold font-mono", accentClass)}>
        {value}
      </div>
      <div className="flex items-center gap-2 mt-1">
        {trend && (
          <span
            className={cn(
              "text-[11px] font-medium",
              trend.direction === "up" ? "text-success" : "text-error",
            )}
          >
            {trend.direction === "up" ? "↑" : "↓"} {trend.value}
          </span>
        )}
        {subtitle && <span className="text-[10px] text-text-muted">{subtitle}</span>}
      </div>
    </div>
  );
}

function RoiGauge({ value, max = 10000 }: { value: number; max?: number }) {
  const clamped = Math.min(max, Math.max(0, value));
  const pct = (clamped / max) * 100;
  const label =
    value > 5000
      ? "Exceptional"
      : value > 1000
      ? "Excellent"
      : value > 500
      ? "Strong"
      : value > 100
      ? "Good"
      : "Moderate";

  return (
    <div className="card p-5 text-center">
      <div className="flex items-center justify-center gap-2 mb-3">
        <Target size={16} className="text-success" />
        <span className="text-sm font-semibold text-text-primary">ROI</span>
      </div>
      <div className="relative inline-flex items-center justify-center">
        <svg width="140" height="140" viewBox="0 0 140 140">
          <circle
            cx="70" cy="70" r="60"
            fill="none" stroke="#27272C" strokeWidth="10"
          />
          <circle
            cx="70" cy="70" r="60"
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${(pct / 100) * 376.99} 376.99`}
            transform="rotate(-90 70 70)"
            className="text-success"
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="text-3xl font-bold font-mono text-success">
            {value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value}%
          </span>
          <span className="text-[10px] text-text-muted uppercase tracking-wider mt-0.5">
            {label}
          </span>
        </div>
      </div>
    </div>
  );
}

function InputSlider({
  label,
  value,
  min,
  max,
  step = 1,
  format = "number",
  onChange,
  icon: Icon,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  format?: "number" | "currency";
  onChange: (v: number) => void;
  icon: React.ElementType;
}) {
  const displayValue = format === "currency" ? `$${value.toLocaleString()}` : String(value);

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon size={14} className="text-forge-primary" />
          <span className="text-xs font-medium text-text-primary">{label}</span>
        </div>
        <span className="text-sm font-mono font-bold text-forge-primary">{displayValue}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-forge-elevated rounded-full appearance-none cursor-pointer
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-forge-primary
          [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:shadow-lg"
      />
      <div className="flex justify-between text-[10px] text-text-muted mt-1.5">
        <span>{format === "currency" ? `$${min.toLocaleString()}` : min}</span>
        <span>{format === "currency" ? `$${max.toLocaleString()}` : max}</span>
      </div>
    </div>
  );
}

// ─── Tier Breakdown ─────────────────────────────────────────────

function TierBreakdown({ teamSize, currentRate, projectedRate }: {
  teamSize: number;
  currentRate: number;
  projectedRate: number;
}) {
  const tiers = [
    { label: "Free", devs: 1, cost: 0, desc: "1 dev, no training" },
    { label: "Go", devs: 1, cost: 9, desc: "1 dev, weekly QLoRA" },
    { label: "Team", devs: 5, cost: 49, desc: "5 devs, daily training" },
    { label: "Scale", devs: 20, cost: 199, desc: "20 devs, SEAL" },
    { label: "Enterprise", devs: Infinity, cost: 3000, desc: "Unlimited, compliance" },
  ];

  const selectedIdx = tiers.findIndex((t) => teamSize <= t.devs);
  const selected = selectedIdx >= 0 ? tiers[selectedIdx] : tiers[tiers.length - 1];

  // Simple per-tier value calculation
  const rateDelta = projectedRate - currentRate;

  return (
    <div className="card p-4">
      <h4 className="text-xs font-semibold text-text-primary mb-3 uppercase tracking-wider flex items-center gap-2">
        <Sliders size={12} className="text-forge-primary" />
        Pricing Tiers
      </h4>
      <div className="space-y-1.5">
        {tiers.map((tier, i) => {
          const isSelected = i === selectedIdx;
          return (
            <div
              key={tier.label}
              className={cn(
                "flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-all",
                isSelected
                  ? "bg-forge-primary/10 ring-1 ring-forge-primary/30"
                  : "text-text-muted",
              )}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    isSelected ? "bg-forge-primary" : "bg-forge-elevated",
                  )}
                />
                <span className={isSelected ? "text-text-primary font-medium" : ""}>
                  {tier.label}
                </span>
                {i === 0 && <span className="text-success text-[10px]">Free</span>}
              </div>
              <span className="font-mono">
                {tier.cost === 0 ? "Free" : `$${tier.cost}/mo`}
              </span>
            </div>
          );
        })}
      </div>
      {selected && (
        <div className="mt-3 pt-3 border-t border-forge-border">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-text-muted">Recommended tier</span>
            <span className="font-medium text-forge-primary">{selected.label}</span>
          </div>
          <p className="text-[10px] text-text-muted mt-0.5">{selected.desc}</p>
        </div>
      )}
    </div>
  );
}

// ─── Training Delta History ─────────────────────────────────────

function TrainingDeltaSparkline({ runs }: { runs: TrainingRun[] }) {
  if (runs.length === 0) return null;
  const deltas = [...runs].reverse().map((r) => r.acceptance_delta * 100);
  const maxDelta = Math.max(...deltas, 1);

  return (
    <div className="flex items-end gap-0.5 h-8">
      {deltas.slice(-12).map((d, i) => (
        <div
          key={i}
          className="flex-1 rounded-t transition-all duration-300"
          style={{
            height: `${(d / maxDelta) * 100}%`,
            backgroundColor: d >= 0 ? "rgba(74,222,128,0.6)" : "rgba(239,68,68,0.6)",
            minHeight: d > 0 ? 2 : 0,
          }}
          title={`Run ${i + 1}: ${d >= 0 ? "+" : ""}${d.toFixed(2)}%`}
        />
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════

interface RoiCalculatorProps {
  initialTeamSize?: number;
  initialSalary?: number;
}

export default function RoiCalculator({
  initialTeamSize = 10,
  initialSalary = 150000,
}: RoiCalculatorProps) {
  // ── State ─────────────────────────────────────────────────────

  const [stats, setStats] = useState<CaptureStats | null>(null);
  const [trainingRuns, setTrainingRuns] = useState<TrainingRun[]>([]);
  const [loading, setLoading] = useState(true);

  const [inputs, setInputs] = useState<RoiInputs>({
    teamSize: initialTeamSize,
    avgSalary: initialSalary,
  });

  const [expanded, setExpanded] = useState(true);

  // ── Fetch data ────────────────────────────────────────────────

  useEffect(() => {
    async function load() {
      try {
        const [s, train] = await Promise.all([
          getCaptureStats().catch(() => null),
          getTrainingStatus().catch(() => ({ active_run: null, history: [] as TrainingRun[] })),
        ]);
        setStats(s);
        setTrainingRuns(train.history);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // ── Derive metrics ────────────────────────────────────────────

  const { currentRate, avgTrainingDelta } = useMemo(() => {
    const rate = stats?.overall_acceptance_rate ?? 50.0;
    const deltas = trainingRuns.map((r) => r.acceptance_delta);
    const avgDelta = deltas.length > 0
      ? deltas.reduce((a, b) => a + b, 0) / deltas.length
      : 0.03; // Default 3% improvement per run
    return { currentRate: rate, avgTrainingDelta: avgDelta * 100 };
  }, [stats, trainingRuns]);

  const results = useMemo(
    () => computeRoi(inputs, currentRate, avgTrainingDelta, trainingRuns.length),
    [inputs, currentRate, avgTrainingDelta, trainingRuns.length],
  );

  // ── Loading ───────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="card p-5 animate-pulse space-y-4">
        <div className="h-5 w-40 bg-forge-elevated rounded" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-forge-elevated rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between group"
      >
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Calculator size={16} className="text-success" />
          ROI Calculator
          <span className="text-[10px] font-normal text-text-muted ml-1">REQ-DASH-004</span>
        </h2>
        <div className="flex items-center gap-2">
          {!expanded && (
            <span className="text-xs font-mono font-semibold text-success">
              {results.roiPercent >= 1000
                ? `${(results.roiPercent / 1000).toFixed(1)}k%`
                : `${results.roiPercent}%`}{" "}
              ROI
            </span>
          )}
          {expanded ? (
            <ChevronUp size={16} className="text-text-muted" />
          ) : (
            <ChevronDown size={16} className="text-text-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <>
          {/* Summary row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <ValueDisplay
              label="Annual Value"
              value={formatCurrency(results.annualValueTotal)}
              icon={DollarSign}
              accent="text-success"
              subtitle="Productivity gain"
            />
            <ValueDisplay
              label="Net Savings"
              value={formatCurrency(results.netAnnualSavings)}
              icon={Zap}
              accent={results.netAnnualSavings >= 0 ? "text-success" : "text-error"}
              subtitle={`After $${results.forgeaiAnnualCost.toLocaleString()}/yr cost`}
            />
            <ValueDisplay
              label="Acceptance Rate"
              value={`${results.currentRate.toFixed(1)}%`}
              icon={TrendingUp}
              accent="text-forge-primary"
              trend={{
                direction: results.projectedRate > results.currentRate ? "up" : "down",
                value: `→ ${results.projectedRate.toFixed(1)}%`,
              }}
            />
            <ValueDisplay
              label="Productivity Gain"
              value={`${results.productivityGainPct.toFixed(1)}%`}
              icon={Brain}
              accent="text-cyan-400"
              subtitle={`${teamSizeLabel(inputs.teamSize)} team`}
            />
          </div>

          {/* Main grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Left: ROI Gauge + key stats */}
            <div className="space-y-4">
              <RoiGauge value={results.roiPercent} max={10000} />

              {/* Payback & Tier */}
              <div className="card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-text-muted uppercase tracking-wider">Payback</span>
                  <span className="text-xs font-mono font-bold text-success">
                    ~{results.paybackDays} day{results.paybackDays !== 1 ? "s" : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-text-muted uppercase tracking-wider">Tier</span>
                  <span className="text-xs font-mono font-bold text-forge-primary">
                    {results.tier}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-text-muted uppercase tracking-wider">ROI</span>
                  <span className="text-xs font-mono font-bold text-success">
                    {results.roiPercent >= 1000
                      ? `${(results.roiPercent / 1000).toFixed(1)}k`
                      : results.roiPercent}
                    %
                  </span>
                </div>
              </div>

              {/* Training delta sparkline */}
              {trainingRuns.length > 0 && (
                <div className="card p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] text-text-muted uppercase tracking-wider">
                      Training Run Deltas
                    </span>
                    <span className="text-[10px] font-mono text-text-muted">
                      avg: +{avgTrainingDelta.toFixed(1)}%
                    </span>
                  </div>
                  <TrainingDeltaSparkline runs={trainingRuns} />
                </div>
              )}
            </div>

            {/* Middle: Input controls */}
            <div className="space-y-3">
              <InputSlider
                label="Team Size"
                value={inputs.teamSize}
                min={1}
                max={100}
                onChange={(v) => setInputs((p) => ({ ...p, teamSize: v }))}
                icon={Users}
              />
              <InputSlider
                label="Avg Annual Salary"
                value={inputs.avgSalary}
                min={50000}
                max={350000}
                step={5000}
                format="currency"
                onChange={(v) => setInputs((p) => ({ ...p, avgSalary: v }))}
                icon={DollarSign}
              />
            </div>

            {/* Right: Pricing tiers */}
            <TierBreakdown
              teamSize={inputs.teamSize}
              currentRate={results.currentRate}
              projectedRate={results.projectedRate}
            />
          </div>

          {/* Bottom: Detailed breakdown */}
          <div className="card p-4">
            <h4 className="text-[10px] text-text-muted uppercase tracking-wider font-medium mb-3">
              Calculation Breakdown
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
              <div>
                <span className="text-text-muted">Team Size</span>
                <p className="font-mono font-medium text-text-primary mt-0.5">
                  {inputs.teamSize} developer{inputs.teamSize !== 1 ? "s" : ""}
                </p>
              </div>
              <div>
                <span className="text-text-muted">Avg Salary</span>
                <p className="font-mono font-medium text-text-primary mt-0.5">
                  ${inputs.avgSalary.toLocaleString()}
                </p>
              </div>
              <div>
                <span className="text-text-muted">Rate Improvement</span>
                <p className="font-mono font-medium text-success mt-0.5">
                  +{(results.projectedRate - results.currentRate).toFixed(1)}pp
                </p>
              </div>
              <div>
                <span className="text-text-muted">ForgeAI Cost</span>
                <p className="font-mono font-medium text-text-primary mt-0.5">
                  ${results.forgeaiAnnualCost.toLocaleString()}/yr
                </p>
              </div>
            </div>
          </div>

          {/* Timestamp & disclaimer */}
          <p className="text-[9px] text-text-muted text-center">
            Based on current acceptance rate ({results.currentRate.toFixed(1)}%) and{" "}
            {trainingRuns.length} training run{trainingRuns.length !== 1 ? "s" : ""}.
            Projected over 3 months. Adjust sliders to see different scenarios.
          </p>
        </>
      )}
    </div>
  );
}

// ─── Helper ─────────────────────────────────────────────────────

function teamSizeLabel(size: number): string {
  if (size <= 1) return "solo";
  if (size <= 5) return "small";
  if (size <= 20) return "medium";
  if (size <= 50) return "large";
  return "enterprise";
}
