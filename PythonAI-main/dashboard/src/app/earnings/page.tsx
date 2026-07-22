"use client";

import { useState, useEffect } from "react";
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Wallet,
  Banknote,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  RefreshCw,
  BarChart3,
  PieChart,
  Users,
  Download,
  ArrowUpRight,
  Send,
  FileText,
  Star,
  Copy,
} from "lucide-react";

interface EarningsData {
  author: string;
  total_adapters: number;
  paid_adapters: number;
  free_adapters: number;
  total_earnings_cents: number;
  total_earnings_dollars: number;
  platform_fees_cents: number;
  platform_fees_dollars: number;
  pending_payout_cents: number;
  pending_payout_dollars: number;
  paid_out_cents: number;
  paid_out_dollars: number;
  in_flight_payouts_cents: number;
  in_flight_payouts_dollars: number;
  total_revenue_cents: number;
  total_revenue_dollars: number;
  num_earnings_events: number;
  by_adapter: Array<{
    adapter_id: string;
    adapter_name: string;
    price_cents: number;
    downloads: number;
    total_earned_cents: number;
    platform_share_cents: number;
    pending_payout_cents: number;
    last_earning: number;
  }>;
  recent_earnings: Array<{
    id: string;
    adapter_id: string;
    adapter_name: string;
    amount_cents: number;
    creator_share_cents: number;
    platform_share_cents: number;
    event_type: string;
    created_at: number;
  }>;
}

interface PayoutRecord {
  id: string;
  author: string;
  amount_cents: number;
  fee_cents: number;
  status: string;
  method: string;
  destination: string;
  notes: string;
  created_at: number;
  processed_at: number | null;
}

interface RevenueStats {
  total_revenue_cents: number;
  total_revenue_dollars: number;
  total_creator_earnings_cents: number;
  total_creator_earnings_dollars: number;
  total_platform_fees_cents: number;
  total_platform_fees_dollars: number;
  total_paid_out_cents: number;
  total_paid_out_dollars: number;
  pending_payouts_cents: number;
  pending_payouts_dollars: number;
  split_ratio: string;
  min_payout_dollars: number;
  total_paid_adapters: number;
  total_downloads_paid: number;
  unique_creators: number;
  total_earnings_events: number;
  total_payouts: number;
  pending_payouts_count: number;
  completed_payouts_count: number;
  top_earners: Array<{ author: string; earned_cents: number; earned_dollars: number }>;
  monthly_breakdown: Array<{
    month: string;
    revenue_dollars: number;
    creator_dollars: number;
    platform_dollars: number;
    transactions: number;
  }>;
  config: {
    creator_share: number;
    platform_share: number;
    min_payout_cents: number;
    payout_methods: string[];
  };
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatDateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function EarningsPage() {
  const [author, setAuthor] = useState("ForgeAI Team");
  const [earnings, setEarnings] = useState<EarningsData | null>(null);
  const [payouts, setPayouts] = useState<PayoutRecord[]>([]);
  const [revenueStats, setRevenueStats] = useState<RevenueStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [payoutLoading, setPayoutLoading] = useState(false);
  const [payoutMethod, setPayoutMethod] = useState("bank");
  const [payoutDest, setPayoutDest] = useState("");
  const [payoutResult, setPayoutResult] = useState<{ success: boolean; message: string } | null>(null);

  useEffect(() => {
    fetchAll();
  }, [author]);

  async function fetchAll() {
    setLoading(true);
    await Promise.all([fetchEarnings(), fetchPayouts(), fetchRevenueStats()]);
    setLoading(false);
  }

  async function fetchEarnings() {
    try {
      const res = await fetch(
        `http://localhost:7337/api/marketplace/earnings/${encodeURIComponent(author)}`
      );
      const data = await res.json();
      if (data.success) setEarnings(data.earnings);
    } catch (e) {
      console.error("Failed to fetch earnings:", e);
    }
  }

  async function fetchPayouts() {
    try {
      const res = await fetch(
        `http://localhost:7337/api/marketplace/payouts?author=${encodeURIComponent(author)}`
      );
      const data = await res.json();
      if (data.success) setPayouts(data.payouts);
    } catch (e) {
      console.error("Failed to fetch payouts:", e);
    }
  }

  async function fetchRevenueStats() {
    try {
      const res = await fetch("http://localhost:7337/api/marketplace/revenue/stats");
      const data = await res.json();
      if (data.success) setRevenueStats(data.stats);
    } catch (e) {
      console.error("Failed to fetch revenue stats:", e);
    }
  }

  async function handleRequestPayout() {
    setPayoutLoading(true);
    setPayoutResult(null);
    try {
      const res = await fetch("http://localhost:7337/api/marketplace/payouts/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          author,
          method: payoutMethod,
          destination: payoutDest,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setPayoutResult({ success: true, message: data.message });
        // Refresh data after payout
        setTimeout(() => fetchAll(), 1000);
      } else {
        setPayoutResult({ success: false, message: data.detail || data.error || "Payout failed" });
      }
    } catch (e) {
      setPayoutResult({ success: false, message: "Network error" });
    } finally {
      setPayoutLoading(false);
    }
  }

  function getStatusBadge(status: string) {
    const styles: Record<string, string> = {
      completed: "bg-success/10 text-success",
      pending: "bg-warning/10 text-warning",
      processing: "bg-info/10 text-info",
      failed: "bg-error/10 text-error",
      cancelled: "bg-text-muted/10 text-text-muted",
    };
    return styles[status] || "bg-forge-elevated text-text-muted";
  }

  function getStatusIcon(status: string) {
    switch (status) {
      case "completed": return <CheckCircle size={14} />;
      case "pending":
      case "processing": return <Clock size={14} />;
      case "failed":
      case "cancelled": return <XCircle size={14} />;
      default: return <AlertTriangle size={14} />;
    }
  }

  const pendingAmount = earnings?.pending_payout_cents || 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-3">
            <DollarSign className="w-7 h-7 text-forge-primary" />
            Creator Earnings
          </h1>
          <p className="text-text-muted mt-1">
            Track your revenue, manage payouts, and monitor adapter performance
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Users size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Creator name..."
              className="input pl-9 w-48 text-sm"
            />
          </div>
          <button onClick={fetchAll} className="btn-ghost p-2 text-text-muted hover:text-text-primary">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-forge-primary" />
        </div>
      ) : earnings ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="card p-4 border-l-4 border-l-forge-primary">
              <p className="text-xs text-text-muted mb-1">Total Earned (70% share)</p>
              <p className="text-2xl font-bold text-forge-primary">
                {formatCents(earnings.total_earnings_cents)}
              </p>
              <p className="text-xs text-text-muted mt-1">
                {earnings.num_earnings_events} transactions
              </p>
            </div>
            <div className="card p-4 border-l-4 border-l-warning">
              <p className="text-xs text-text-muted mb-1">Platform Fees (30% share)</p>
              <p className="text-2xl font-bold text-warning">
                {formatCents(earnings.platform_fees_cents)}
              </p>
              <p className="text-xs text-text-muted mt-1">Revenue split: {revenueStats?.split_ratio || "70/30"}</p>
            </div>
            <div className="card p-4 border-l-4 border-l-success">
              <p className="text-xs text-text-muted mb-1">Available for Payout</p>
              <p className="text-2xl font-bold text-success">
                {formatCents(earnings.pending_payout_cents)}
              </p>
              <p className="text-xs text-text-muted mt-1">
                Min. ${revenueStats?.min_payout_dollars.toFixed(2) || "5.00"}
              </p>
            </div>
            <div className="card p-4 border-l-4 border-l-info">
              <p className="text-xs text-text-muted mb-1">Paid Out</p>
              <p className="text-2xl font-bold text-info">
                {formatCents(earnings.paid_out_cents)}
              </p>
              <p className="text-xs text-text-muted mt-1">
                {payouts.filter((p) => p.status === "completed").length} payouts
              </p>
            </div>
          </div>

          {/* Revenue Split Visual */}
          {earnings.total_revenue_cents > 0 && (
            <div className="card p-6">
              <h3 className="font-semibold text-text-primary flex items-center gap-2 mb-4">
                <PieChart size={16} className="text-forge-primary" />
                Revenue Split
              </h3>
              <div className="flex items-center gap-6">
                <div className="relative w-32 h-32">
                  <svg viewBox="0 0 36 36" className="w-32 h-32 -rotate-90">
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="3"
                      className="text-forge-elevated" />
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="currentColor" strokeWidth="3"
                      strokeDasharray={`${revenueStats?.config.creator_share || 0.7 * 100} ${revenueStats?.config.platform_share || 0.3 * 100}`}
                      strokeDashoffset="0"
                      className="text-forge-primary"
                      style={{ strokeDasharray: `${(revenueStats?.config.creator_share || 0.7) * 100} ${(revenueStats?.config.platform_share || 0.3) * 100}` }}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center">
                      <p className="text-lg font-bold text-text-primary">{revenueStats?.split_ratio || "70/30"}</p>
                      <p className="text-[10px] text-text-muted">Split</p>
                    </div>
                  </div>
                </div>
                <div className="space-y-3 flex-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-sm bg-forge-primary" />
                      <span className="text-sm text-text-primary">Creator Share ({(revenueStats?.config.creator_share || 0.7) * 100}%)</span>
                    </div>
                    <span className="text-sm font-semibold text-text-primary">
                      {formatCents(earnings.total_earnings_cents)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-sm bg-warning" />
                      <span className="text-sm text-text-primary">Platform Share ({(revenueStats?.config.platform_share || 0.3) * 100}%)</span>
                    </div>
                    <span className="text-sm font-semibold text-text-primary">
                      {formatCents(earnings.platform_fees_cents)}
                    </span>
                  </div>
                  <div className="pt-2 border-t border-forge-border">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-text-muted">Total Revenue</span>
                      <span className="font-bold text-text-primary">
                        {formatCents(earnings.total_revenue_cents)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Payout Request */}
          <div className="card p-6">
            <h3 className="font-semibold text-text-primary flex items-center gap-2 mb-4">
              <Send size={16} className="text-forge-primary" />
              Request Payout
            </h3>
            {pendingAmount > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex-1 min-w-[200px]">
                    <label className="block text-xs text-text-muted mb-1">Method</label>
                    <select
                      value={payoutMethod}
                      onChange={(e) => setPayoutMethod(e.target.value)}
                      className="input w-full"
                    >
                      <option value="bank">Bank Transfer</option>
                      <option value="paypal">PayPal</option>
                      <option value="crypto">Cryptocurrency</option>
                    </select>
                  </div>
                  <div className="flex-[2] min-w-[240px]">
                    <label className="block text-xs text-text-muted mb-1">Destination</label>
                    <input
                      type="text"
                      value={payoutDest}
                      onChange={(e) => setPayoutDest(e.target.value)}
                      placeholder={
                        payoutMethod === "bank"
                          ? "Account number / routing"
                          : payoutMethod === "paypal"
                            ? "Email address"
                            : "Wallet address"
                      }
                      className="input w-full"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-text-muted">
                      Available: <span className="font-semibold text-success">{formatCents(pendingAmount)}</span>
                    </p>
                    {revenueStats && (
                      <p className="text-xs text-text-muted">
                        Min payout: ${revenueStats.min_payout_dollars.toFixed(2)}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={handleRequestPayout}
                    disabled={payoutLoading}
                    className="btn-primary px-5 py-2 text-sm flex items-center gap-2"
                  >
                    {payoutLoading ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Send size={16} />
                    )}
                    {payoutLoading ? "Processing..." : `Request Payout (${formatCents(pendingAmount)})`}
                  </button>
                </div>
                {payoutResult && (
                  <div
                    className={`text-sm p-3 rounded-lg ${
                      payoutResult.success
                        ? "bg-success/10 text-success border border-success/20"
                        : "bg-error/10 text-error border border-error/20"
                    }`}
                  >
                    {payoutResult.success ? (
                      <div className="flex items-center gap-2">
                        <CheckCircle size={16} />
                        {payoutResult.message}
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <AlertTriangle size={16} />
                        {payoutResult.message}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-6 text-text-muted">
                <Banknote size={32} className="mx-auto mb-2" />
                <p>No pending earnings available for payout</p>
                <p className="text-xs mt-1">Earnings appear here when paid adapters are installed</p>
              </div>
            )}
          </div>

          {/* Per-Adapter Breakdown */}
          <div className="card p-6">
            <h3 className="font-semibold text-text-primary flex items-center gap-2 mb-4">
              <BarChart3 size={16} className="text-forge-primary" />
              Per-Adapter Earnings
            </h3>
            {earnings.by_adapter.length === 0 ? (
              <p className="text-text-muted text-sm py-4 text-center">No adapters with earnings yet</p>
            ) : (
              <div className="space-y-3">
                {earnings.by_adapter.map((adap) => (
                  <div
                    key={adap.adapter_id}
                    className="flex items-center justify-between p-3 rounded-lg bg-forge-elevated/50 hover:bg-forge-elevated transition-colors"
                  >
                    <div className="flex-1">
                      <p className="text-sm font-medium text-text-primary">{adap.adapter_name}</p>
                      <div className="flex items-center gap-3 text-xs text-text-muted mt-1">
                        {adap.price_cents > 0 ? (
                          <span className="text-forge-primary font-medium">
                            {formatCents(adap.price_cents)}
                          </span>
                        ) : (
                          <span className="text-success">Free</span>
                        )}
                        <span>{adap.downloads} downloads</span>
                        {adap.last_earning > 0 && (
                          <span>Last: {formatDate(adap.last_earning)}</span>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-forge-primary">
                        {formatCents(adap.total_earned_cents)}
                      </p>
                      <p className="text-xs text-text-muted">earned</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Payout History */}
          <div className="card p-6">
            <h3 className="font-semibold text-text-primary flex items-center gap-2 mb-4">
              <FileText size={16} className="text-forge-primary" />
              Payout History
            </h3>
            {payouts.length === 0 ? (
              <p className="text-text-muted text-sm py-4 text-center">No payout history yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-forge-border">
                      <th className="text-left py-2 px-3 text-text-muted font-medium">Date</th>
                      <th className="text-left py-2 px-3 text-text-muted font-medium">Amount</th>
                      <th className="text-left py-2 px-3 text-text-muted font-medium">Method</th>
                      <th className="text-left py-2 px-3 text-text-muted font-medium">Status</th>
                      <th className="text-left py-2 px-3 text-text-muted font-medium">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payouts.map((p) => (
                      <tr key={p.id} className="border-b border-forge-border/50 hover:bg-forge-elevated/30 transition-colors">
                        <td className="py-2.5 px-3 text-text-primary">
                          {formatDateTime(p.created_at)}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="font-semibold text-text-primary">
                            {formatCents(p.amount_cents)}
                          </span>
                          {p.fee_cents > 0 && (
                            <span className="text-xs text-text-muted ml-1">
                              (fee: {formatCents(p.fee_cents)})
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-text-primary capitalize">{p.method}</td>
                        <td className="py-2.5 px-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${getStatusBadge(p.status)}`}>
                            {getStatusIcon(p.status)}
                            {p.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-text-muted text-xs">{p.notes || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Recent Earnings Events */}
          <div className="card p-6">
            <h3 className="font-semibold text-text-primary flex items-center gap-2 mb-4">
              <TrendingUp size={16} className="text-forge-primary" />
              Recent Transactions
            </h3>
            {earnings.recent_earnings.length === 0 ? (
              <p className="text-text-muted text-sm py-4 text-center">No recent earnings</p>
            ) : (
              <div className="space-y-2">
                {earnings.recent_earnings.map((e) => (
                  <div
                    key={e.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-forge-elevated/30 hover:bg-forge-elevated/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-forge-primary/20 flex items-center justify-center">
                        <Download size={14} className="text-forge-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-text-primary">{e.adapter_name}</p>
                        <p className="text-xs text-text-muted">{formatDateTime(e.created_at)}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-forge-primary">
                        +{formatCents(e.creator_share_cents)}
                      </p>
                      <p className="text-xs text-text-muted">70% of {formatCents(e.amount_cents)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Platform Revenue Stats */}
          {revenueStats && (
            <div className="card p-6">
              <h3 className="font-semibold text-text-primary flex items-center gap-2 mb-4">
                <BarChart3 size={16} className="text-forge-primary" />
                Platform Revenue Overview
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div>
                  <p className="text-xs text-text-muted">Total Platform Revenue</p>
                  <p className="text-lg font-bold text-text-primary">
                    {formatCents(revenueStats.total_revenue_cents)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Paid to Creators</p>
                  <p className="text-lg font-bold text-success">
                    {formatCents(revenueStats.total_paid_out_cents)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Platform Fees Collected</p>
                  <p className="text-lg font-bold text-warning">
                    {formatCents(revenueStats.total_platform_fees_cents)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Unique Creators</p>
                  <p className="text-lg font-bold text-info">{revenueStats.unique_creators}</p>
                </div>
              </div>

              {/* Monthly Breakdown */}
              {revenueStats.monthly_breakdown.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-text-primary mb-3">Monthly Revenue</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-forge-border">
                          <th className="text-left py-2 px-3 text-text-muted font-medium">Month</th>
                          <th className="text-right py-2 px-3 text-text-muted font-medium">Revenue</th>
                          <th className="text-right py-2 px-3 text-text-muted font-medium">Creator Share</th>
                          <th className="text-right py-2 px-3 text-text-muted font-medium">Platform Fee</th>
                          <th className="text-right py-2 px-3 text-text-muted font-medium">Transactions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {revenueStats.monthly_breakdown.map((m) => (
                          <tr key={m.month} className="border-b border-forge-border/30 hover:bg-forge-elevated/30 transition-colors">
                            <td className="py-2 px-3 text-text-primary font-medium">{m.month}</td>
                            <td className="py-2 px-3 text-right text-text-primary">${m.revenue_dollars.toFixed(2)}</td>
                            <td className="py-2 px-3 text-right text-success">${m.creator_dollars.toFixed(2)}</td>
                            <td className="py-2 px-3 text-right text-warning">${m.platform_dollars.toFixed(2)}</td>
                            <td className="py-2 px-3 text-right text-text-muted">{m.transactions}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Top Earners */}
              {revenueStats.top_earners.length > 0 && (
                <div className="mt-6">
                  <h4 className="text-sm font-medium text-text-primary mb-3 flex items-center gap-2">
                    <Star size={14} className="text-warning" />
                    Top Earners
                  </h4>
                  <div className="space-y-2">
                    {revenueStats.top_earners.map((e, i) => (
                      <div key={e.author} className="flex items-center justify-between p-2 rounded-lg bg-forge-elevated/30">
                        <div className="flex items-center gap-3">
                          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                            i === 0 ? "bg-warning/20 text-warning" :
                            i === 1 ? "bg-forge-elevated text-text-muted" :
                            i === 2 ? "bg-amber-500/20 text-amber-600" :
                            "bg-forge-elevated text-text-muted"
                          }`}>
                            {i + 1}
                          </span>
                          <span className="text-sm text-text-primary">{e.author}</span>
                        </div>
                        <span className="text-sm font-semibold text-forge-primary">{formatCents(e.earned_cents)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-20">
          <DollarSign size={48} className="mx-auto text-text-muted mb-4" />
          <p className="text-text-muted">No earnings data found for &quot;{author}&quot;</p>
          <p className="text-xs text-text-muted mt-1">Try a different creator name</p>
        </div>
      )}
    </div>
  );
}
