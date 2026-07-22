"use client";

import { useState, useEffect } from "react";
import {
  Search,
  Download,
  Star,
  TrendingUp,
  Shield,
  Check,
  X,
  Zap,
  Code,
  Layers,
  Filter,
  ArrowUpDown,
  CheckCircle,
  Loader2,
  ExternalLink,
} from "lucide-react";

interface Adapter {
  id: string;
  name: string;
  description: string;
  author: string;
  version: string;
  base_model: string;
  framework: string;
  industry: string;
  tags: string[];
  file_size_bytes: number;
  downloads: number;
  rating: number;
  acceptance_improvement: number;
  installed: boolean;
  is_verified: boolean;
  sanitization_score: number;
}

export default function SkillsPage() {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [installing, setInstalling] = useState<string | null>(null);
  const [stats, setStats] = useState({
    total_adapters: 0,
    installed: 0,
    total_downloads: 0,
    avg_rating: 0,
    frameworks: [] as string[],
    industries: [] as string[],
  });

  useEffect(() => {
    fetchAdapters();
    fetchStats();
  }, []);

  async function fetchAdapters(params?: string) {
    setLoading(true);
    try {
      const url = params
        ? `http://localhost:7337/api/marketplace/adapters${params}`
        : "http://localhost:7337/api/marketplace/adapters";
      const res = await fetch(url);
      const data = await res.json();
      if (data.success) setAdapters(data.adapters);
    } catch (e) {
      console.error("Failed to fetch adapters:", e);
    } finally {
      setLoading(false);
    }
  }

  async function fetchStats() {
    try {
      const res = await fetch("http://localhost:7337/api/marketplace/stats");
      const data = await res.json();
      if (data.success) setStats(data.stats);
    } catch (e) {
      console.error("Failed to fetch stats:", e);
    }
  }

  async function handleInstall(adapterId: string) {
    setInstalling(adapterId);
    try {
      await fetch("http://localhost:7337/api/marketplace/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ adapter_id: adapterId }),
      });
      setAdapters((prev) =>
        prev.map((a) => (a.id === adapterId ? { ...a, installed: true, downloads: a.downloads + 1 } : a)),
      );
      fetchStats();
    } catch (e) {
      console.error("Failed to install:", e);
    } finally {
      setInstalling(null);
    }
  }

  async function handleUninstall(adapterId: string) {
    try {
      await fetch("http://localhost:7337/api/marketplace/uninstall", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ adapter_id: adapterId }),
      });
      setAdapters((prev) =>
        prev.map((a) => (a.id === adapterId ? { ...a, installed: false } : a)),
      );
      fetchStats();
    } catch (e) {
      console.error("Failed to uninstall:", e);
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (category) params.set("framework", category);
    fetchAdapters(`?${params.toString()}`);
  }

  const filtered = adapters.filter((a) => {
    if (search && !a.name.toLowerCase().includes(search.toLowerCase()) && !a.description.toLowerCase().includes(search.toLowerCase())) return false;
    if (category && a.framework !== category && !a.tags.includes(category)) return false;
    return true;
  });

  function formatBytes(bytes: number): string {
    if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
    if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`;
    return `${bytes} B`;
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary flex items-center gap-3">
          <Layers className="w-7 h-7 text-forge-primary" />
          Skills Marketplace
        </h1>
        <p className="text-text-muted mt-1">
          Browse, install, and compose fine-tuned adapters from the community
        </p>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-forge-primary/20 flex items-center justify-center">
              <Layers size={20} className="text-forge-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text-primary">{stats.total_adapters}</p>
              <p className="text-xs text-text-muted">Available</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-success/20 flex items-center justify-center">
              <CheckCircle size={20} className="text-success" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text-primary">{stats.installed}</p>
              <p className="text-xs text-text-muted">Installed</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-warning/20 flex items-center justify-center">
              <Download size={20} className="text-warning" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text-primary">{stats.total_downloads.toLocaleString()}</p>
              <p className="text-xs text-text-muted">Downloads</p>
            </div>
          </div>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-info/20 flex items-center justify-center">
              <Star size={20} className="text-info" />
            </div>
            <div>
              <p className="text-2xl font-bold text-text-primary">{stats.avg_rating}</p>
              <p className="text-xs text-text-muted">Avg Rating</p>
            </div>
          </div>
        </div>
      </div>

      {/* Search & Filters */}
      <form onSubmit={handleSearch} className="flex gap-3 flex-wrap">
        <div className="flex-1 min-w-[240px] relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search adapters..."
            className="input pl-10 w-full"
          />
        </div>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="input w-40"
        >
          <option value="">All Categories</option>
          <option value="general">General</option>
          <option value="web">Web</option>
          <option value="backend">Backend</option>
          <option value="data">Data</option>
          <option value="systems">Systems</option>
          <option value="mobile">Mobile</option>
          <option value="devops">DevOps</option>
        </select>
        <button type="submit" className="btn-primary flex items-center gap-2">
          <Filter size={16} />
          Filter
        </button>
      </form>

      {/* Adapter Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-forge-primary" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20">
          <Layers size={48} className="mx-auto text-text-muted mb-4" />
          <p className="text-text-muted">No adapters found</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((adapter) => (
            <div
              key={adapter.id}
              className="card p-5 hover:border-forge-primary/30 transition-all duration-200 group"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-forge-elevated flex items-center justify-center">
                    <Zap size={20} className="text-forge-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-text-primary group-hover:text-forge-primary transition-colors">
                      {adapter.name}
                    </h3>
                    <p className="text-xs text-text-muted">by {adapter.author}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Star size={14} className="text-warning fill-current" />
                  <span className="text-sm font-medium text-text-primary">{adapter.rating}</span>
                </div>
              </div>

              {/* Description */}
              <p className="text-sm text-text-secondary mb-4 line-clamp-2">{adapter.description}</p>

              {/* Tags */}
              <div className="flex flex-wrap gap-1.5 mb-4">
                {adapter.tags.slice(0, 4).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 text-xs rounded-full bg-forge-elevated text-text-muted"
                  >
                    {tag}
                  </span>
                ))}
                {adapter.is_verified && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-success/10 text-success flex items-center gap-1">
                    <Shield size={10} />
                    Verified
                  </span>
                )}
              </div>

              {/* Metadata */}
              <div className="flex items-center justify-between text-xs text-text-muted mb-4 pb-4 border-b border-forge-border">
                <span>{formatBytes(adapter.file_size_bytes)}</span>
                <span className="flex items-center gap-1">
                  <Download size={12} />
                  {adapter.downloads.toLocaleString()}
                </span>
                {adapter.acceptance_improvement > 0 && (
                  <span className="flex items-center gap-1 text-success">
                    <TrendingUp size={12} />
                    +{adapter.acceptance_improvement}%
                  </span>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                {adapter.installed ? (
                  <button
                    onClick={() => handleUninstall(adapter.id)}
                    className="btn-ghost flex-1 text-sm flex items-center justify-center gap-1.5 text-text-muted hover:text-error"
                  >
                    <X size={14} />
                    Uninstall
                  </button>
                ) : (
                  <button
                    onClick={() => handleInstall(adapter.id)}
                    disabled={installing === adapter.id}
                    className="btn-primary flex-1 text-sm flex items-center justify-center gap-1.5"
                  >
                    {installing === adapter.id ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Download size={14} />
                    )}
                    {installing === adapter.id ? "Installing..." : "Install"}
                  </button>
                )}
                <button className="btn-ghost p-2 text-text-muted hover:text-text-primary">
                  <ExternalLink size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
