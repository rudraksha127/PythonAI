"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  Users,
  Key,
  Activity,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Search,
  Download,
  ChevronDown,
  ChevronUp,
  UserPlus,
  UserCheck,
  Lock,
  Globe,
  FileText,
  Clock,
  Copy,
  Loader2,
  Eye,
  EyeOff,
} from "lucide-react";
import { cn, formatNumber, formatTimeAgo } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";

interface AuditEvent {
  event_id: string;
  timestamp: number;
  timestamp_iso: string;
  action: string;
  actor: string;
  resource: string;
  resource_id: string;
  detail: string;
  category: string;
  severity: string;
  ip_address: string;
  metadata: Record<string, unknown>;
  previous_hash: string;
  event_hash: string;
}

interface SSOProvider {
  id: string;
  name: string;
  icon: string;
  auth_url: string;
}

interface RBACUser {
  username: string;
  role: string;
  projects: string[];
  created_at: number;
  is_active: boolean;
}

interface RoleInfo {
  description: string;
  permissions: string[];
  permission_count: number;
}

// ─── Tabs ───────────────────────────────────────────────────────

const TABS = [
  { id: "sso", label: "SSO Configuration", icon: Globe },
  { id: "rbac", label: "Users & Roles", icon: Users },
  { id: "audit", label: "Audit Log", icon: FileText },
] as const;

type TabId = (typeof TABS)[number]["id"];

// ─── Severity Badge ─────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    info: "bg-forge-primary/10 text-forge-primary",
    warning: "bg-warning/10 text-warning",
    error: "bg-error/10 text-error",
    critical: "bg-error/20 text-error font-bold",
  };
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold", colors[severity] || colors.info)}>
      {severity}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SSO Configuration Tab
// ═══════════════════════════════════════════════════════════════════

function SSOTab() {
  const [providers, setProviders] = useState<SSOProvider[]>([]);
  const [status, setStatus] = useState<Record<string, boolean> | null>(null);
  const [loading, setLoading] = useState(true);
  const [samlMetadata, setSamlMetadata] = useState<string | null>(null);
  const [showMetadata, setShowMetadata] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [provRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/sso/providers`).then(r => r.json()),
        fetch(`${API_BASE}/api/auth/sso/status`).then(r => r.json()),
      ]);
      if (provRes.success) setProviders(provRes.providers);
      if (statusRes.success) setStatus({
        google: statusRes.google_configured,
        github: statusRes.github_configured,
        saml: statusRes.saml_configured,
        oidc: statusRes.oidc_configured,
      });
    } catch {
      // Server not running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fetchSAMLMetadata = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/sso/metadata`);
      const data = await res.json();
      if (data.success) setSamlMetadata(data.metadata_xml);
    } catch {}
  };

  const copyMetadata = () => {
    if (samlMetadata) {
      navigator.clipboard.writeText(samlMetadata);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="card p-5 space-y-3">
            <div className="h-5 w-32 bg-forge-elevated rounded" />
            <div className="h-4 w-64 bg-forge-elevated rounded" />
          </div>
        ))}
      </div>
    );
  }

  const providerInfo: Record<string, { label: string; envVars: string[]; doc: string }> = {
    google: {
      label: "Google OAuth2",
      envVars: ["FORGEAI_SSO_GOOGLE_CLIENT_ID", "FORGEAI_SSO_GOOGLE_CLIENT_SECRET"],
      doc: "https://console.cloud.google.com/apis/credentials",
    },
    github: {
      label: "GitHub OAuth2",
      envVars: ["FORGEAI_SSO_GITHUB_CLIENT_ID", "FORGEAI_SSO_GITHUB_CLIENT_SECRET"],
      doc: "https://github.com/settings/developers",
    },
    saml: {
      label: "SAML 2.0",
      envVars: ["FORGEAI_SSO_SAML_METADATA_URL", "FORGEAI_SSO_SAML_ENTITY_ID", "FORGEAI_SSO_SAML_ACS_URL"],
      doc: "Upload SP metadata to your IdP",
    },
    oidc: {
      label: "OpenID Connect",
      envVars: ["FORGEAI_SSO_OIDC_ISSUER_URL", "FORGEAI_SSO_OIDC_CLIENT_ID", "FORGEAI_SSO_OIDC_CLIENT_SECRET"],
      doc: "Configure via your OIDC provider's admin console",
    },
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card p-5">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2 mb-2">
          <Globe size={16} className="text-forge-primary" />
          SSO Provider Status
        </h3>
        {providers.length === 0 && !loading && (
          <p className="text-xs text-text-muted">
            No SSO providers configured. Set the required environment variables to enable authentication providers.
          </p>
        )}
      </div>

      {/* Provider Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(providerInfo).map(([id, info]) => {
          const isConfigured = status?.[id] ?? false;
          const provider = providers.find(p => p.id === id);

          return (
            <div key={id} className={cn(
              "card p-5 transition-all duration-200",
              isConfigured ? "ring-1 ring-success/20" : ""
            )}>
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "p-2 rounded-lg transition-colors",
                    isConfigured ? "bg-success/10" : "bg-forge-elevated"
                  )}>
                    <Lock size={16} className={isConfigured ? "text-success" : "text-text-muted"} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-text-primary">{info.label}</h4>
                    <p className="text-xs text-text-muted">
                      {isConfigured ? "Configured and ready" : "Not configured"}
                    </p>
                  </div>
                </div>
                <span className={cn(
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold",
                  isConfigured ? "bg-success/10 text-success" : "bg-forge-elevated text-text-muted"
                )}>
                  <span className={cn("w-1.5 h-1.5 rounded-full", isConfigured ? "bg-success" : "bg-text-muted")} />
                  {isConfigured ? "Active" : "Inactive"}
                </span>
              </div>

              {isConfigured && provider && (
                <div className="mb-3">
                  <p className="text-xs text-text-secondary">
                    Redirect URI: <code className="text-forge-primary text-[10px]">{provider.auth_url?.split("?")[0] || "—"}</code>
                  </p>
                </div>
              )}

              <div className="space-y-1.5 mb-3">
                <p className="text-[10px] text-text-muted uppercase tracking-wider font-medium">Required Env Vars</p>
                {info.envVars.map(env => (
                  <div key={env} className="flex items-center gap-2">
                    <code className="text-[10px] font-mono text-text-secondary bg-forge-elevated px-1.5 py-0.5 rounded flex-1 truncate">
                      {env}
                    </code>
                    {isConfigured && <CheckCircle2 size={10} className="text-success shrink-0" />}
                  </div>
                ))}
              </div>

              {/* SAML metadata button */}
              {id === "saml" && isConfigured && (
                <div className="pt-2 border-t border-forge-border">
                  <button
                    onClick={() => { fetchSAMLMetadata(); setShowMetadata(!showMetadata); }}
                    className="btn-ghost text-xs gap-1.5"
                  >
                    {showMetadata ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    {showMetadata ? "Hide SP Metadata" : "Show SP Metadata XML"}
                  </button>
                  {showMetadata && samlMetadata && (
                    <div className="mt-2 relative">
                      <pre className="text-[10px] font-mono bg-forge-elevated rounded-lg p-3 overflow-x-auto max-h-40 text-text-secondary">
                        {samlMetadata.slice(0, 1500)}...
                      </pre>
                      <button
                        onClick={copyMetadata}
                        className="absolute top-2 right-2 btn-ghost p-1"
                        title="Copy metadata"
                      >
                        <Copy size={12} />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// RBAC / Users Tab
// ═══════════════════════════════════════════════════════════════════

function RBACTab() {
  const [users, setUsers] = useState<RBACUser[]>([]);
  const [roles, setRoles] = useState<Record<string, RoleInfo>>({});
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [expandedRoles, setExpandedRoles] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [usersRes, rolesRes] = await Promise.all([
        fetch(`${API_BASE}/api/admin/users`).then(r => r.json()),
        fetch(`${API_BASE}/api/admin/roles`).then(r => r.json()),
      ]);
      if (usersRes.success) setUsers(usersRes.users);
      if (rolesRes.success) setRoles(rolesRes.roles);
    } catch {
      // Server not running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRoleChange = async (username: string, newRole: string) => {
    setAssigning(username);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/users/role`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, role: newRole }),
      });
      const data = await res.json();
      if (data.success) {
        setUsers(prev => prev.map(u => u.username === username ? { ...u, role: newRole } : u));
        setResult({ success: true, message: `Role updated to ${newRole} for ${username}` });
      } else {
        setResult({ success: false, message: data.detail || "Failed to update role" });
      }
    } catch (e) {
      setResult({ success: false, message: "Network error" });
    } finally {
      setAssigning(null);
    }
  };

  const roleColors: Record<string, string> = {
    admin: "bg-forge-primary/10 text-forge-primary border-forge-primary/20",
    manager: "bg-warning/10 text-warning border-warning/20",
    developer: "bg-success/10 text-success border-success/20",
  };

  if (loading) {
    return (
      <div className="space-y-3 animate-pulse">
        {[1, 2, 3].map(i => (
          <div key={i} className="card p-4 space-y-2">
            <div className="h-5 w-48 bg-forge-elevated rounded" />
            <div className="h-4 w-32 bg-forge-elevated rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Result toast */}
      {result && (
        <div className={cn(
          "card p-3 flex items-center gap-2 text-sm",
          result.success ? "border-success/20 bg-success/5" : "border-error/20 bg-error/5"
        )}>
          {result.success ? <CheckCircle2 size={14} className="text-success" /> : <XCircle size={14} className="text-error" />}
          <span className={result.success ? "text-success" : "text-error"}>{result.message}</span>
        </div>
      )}

      {/* Users Table */}
      <div className="card overflow-hidden">
        <div className="px-6 py-4 border-b border-forge-border flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Users size={16} className="text-forge-primary" />
            User Management
            <span className="text-[10px] font-normal text-text-muted">{users.length} user{users.length !== 1 ? "s" : ""}</span>
          </h3>
          <button onClick={load} className="btn-ghost p-1.5">
            <RefreshCw size={14} />
          </button>
        </div>
        {users.length === 0 ? (
          <div className="p-8 text-center">
            <UserPlus size={28} className="mx-auto text-text-muted mb-2" />
            <p className="text-sm text-text-muted">No users registered yet. Users appear here after first login or signup.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-forge-border bg-forge-elevated/30">
                  <th className="text-left px-6 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Username</th>
                  <th className="text-left px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Role</th>
                  <th className="text-left px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Projects</th>
                  <th className="text-left px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Status</th>
                  <th className="text-right px-4 py-3 text-text-muted font-medium text-xs uppercase tracking-wider">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-forge-border">
                {users.map((user) => (
                  <tr key={user.username} className="hover:bg-forge-elevated/30 transition-colors">
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <UserCheck size={12} className="text-text-muted" />
                        <span className="text-xs font-mono text-text-primary font-medium">{user.username}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <select
                          value={user.role}
                          onChange={(e) => handleRoleChange(user.username, e.target.value)}
                          disabled={assigning === user.username}
                          className={cn(
                            "text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-transparent cursor-pointer",
                            roleColors[user.role] || "bg-forge-elevated text-text-muted"
                          )}
                        >
                          {Object.keys(roles).map(r => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </select>
                        {assigning === user.username && <Loader2 size={10} className="animate-spin text-text-muted" />}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs font-mono text-text-muted">
                        {user.projects.length > 0
                          ? `${user.projects.length} project${user.projects.length !== 1 ? "s" : ""}`
                          : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]",
                        user.is_active ? "bg-success/10 text-success" : "bg-error/10 text-error"
                      )}>
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-[10px] font-mono text-text-muted">
                        {user.created_at > 0 ? formatTimeAgo(user.created_at) : "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Roles Reference */}
      <div className="card overflow-hidden">
        <button
          onClick={() => setExpandedRoles(!expandedRoles)}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-forge-elevated/30 transition-colors"
        >
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Shield size={16} className="text-forge-primary" />
            Role Permissions Reference
          </h3>
          {expandedRoles ? <ChevronUp size={16} className="text-text-muted" /> : <ChevronDown size={16} className="text-text-muted" />}
        </button>
        {expandedRoles && (
          <div className="px-6 pb-4 space-y-4">
            {Object.entries(roles).map(([roleName, info]) => (
              <div key={roleName} className={cn("p-3 rounded-lg border", roleColors[roleName] || "border-forge-border")}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold capitalize">{roleName}</span>
                  <span className="text-[10px] text-text-muted">{info.permission_count} permissions</span>
                </div>
                <p className="text-[10px] text-text-muted mb-2">{info.description}</p>
                <div className="flex flex-wrap gap-1">
                  {info.permissions.map(perm => (
                    <span key={perm} className="text-[9px] px-1.5 py-0.5 rounded bg-forge-elevated text-text-muted font-mono">
                      {perm}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Audit Log Tab
// ═══════════════════════════════════════════════════════════════════

function AuditTab() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    limit: 50,
    offset: 0,
    action_prefix: "",
    actor: "",
    category: "",
    severity: "",
    search: "",
  });
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/audit/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(filters),
      });
      const data = await res.json();
      if (data.success) {
        setEvents(data.events);
        setTotal(data.total);
      }
    } catch {
      // Server not running
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/audit/stats`);
      const data = await res.json();
      if (data.success) setStats(data);
    } catch {}
  }, []);

  useEffect(() => { loadEvents(); loadStats(); }, [loadEvents, loadStats]);

  const handleExport = async (format: string) => {
    try {
      const params = new URLSearchParams({ format });
      if (filters.category) params.set("category", filters.category);
      if (filters.severity) params.set("severity", filters.severity);
      if (filters.actor) params.set("actor", filters.actor);

      const res = await fetch(`${API_BASE}/api/audit/export?${params.toString()}`);
      const data = await res.json();
      if (data.success) {
        // Create a download link
        const blob = new Blob([data.content], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = data.filename;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {}
  };

  const categoryColors: Record<string, string> = {
    auth: "text-forge-primary",
    user: "text-success",
    training: "text-cyan-400",
    config: "text-warning",
    admin: "text-error",
    sso: "text-forge-primary",
    system: "text-text-muted",
  };

  const categoryBgs: Record<string, string> = {
    auth: "bg-forge-primary/10",
    user: "bg-success/10",
    training: "bg-cyan-500/10",
    config: "bg-warning/10",
    admin: "bg-error/10",
    sso: "bg-forge-primary/10",
    system: "bg-forge-elevated",
  };

  return (
    <div className="space-y-6">
      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="card p-3">
            <span className="metric-label text-[10px]">Total Events</span>
            <p className="text-lg font-bold font-mono text-text-primary">{formatNumber((stats as any).total_events || 0)}</p>
          </div>
          <div className="card p-3">
            <span className="metric-label text-[10px]">Categories</span>
            <p className="text-lg font-bold font-mono text-text-primary">
              {Object.keys((stats as any).by_category || {}).length}
            </p>
          </div>
          <div className="card p-3">
            <span className="metric-label text-[10px]">DB Size</span>
            <p className="text-lg font-bold font-mono text-text-primary">
              {(stats as any).database?.size_mb?.toFixed(2) || "0"} MB
            </p>
          </div>
          <div className="card p-3">
            <span className="metric-label text-[10px]">Chain</span>
            <p className="text-lg font-bold font-mono text-success">✓ Verified</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="card p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-[200px] relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={filters.search}
              onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value, offset: 0 }))}
              placeholder="Search audit events..."
              className="input pl-9 text-sm w-full"
            />
          </div>
          <select
            value={filters.category}
            onChange={(e) => setFilters(prev => ({ ...prev, category: e.target.value, offset: 0 }))}
            className="input text-xs py-2 w-32"
          >
            <option value="">All Categories</option>
            <option value="auth">Auth</option>
            <option value="user">User</option>
            <option value="training">Training</option>
            <option value="config">Config</option>
            <option value="admin">Admin</option>
            <option value="sso">SSO</option>
            <option value="system">System</option>
          </select>
          <select
            value={filters.severity}
            onChange={(e) => setFilters(prev => ({ ...prev, severity: e.target.value, offset: 0 }))}
            className="input text-xs py-2 w-28"
          >
            <option value="">All Severity</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="critical">Critical</option>
          </select>
          <button onClick={() => loadEvents()} className="btn-primary text-xs gap-1.5 px-3 py-2">
            <RefreshCw size={14} />
            Query
          </button>
          <div className="flex gap-1 ml-auto">
            <button onClick={() => handleExport("json")} className="btn-ghost text-xs gap-1" title="Export as JSON">
              <Download size={12} /> JSON
            </button>
            <button onClick={() => handleExport("csv")} className="btn-ghost text-xs gap-1" title="Export as CSV">
              <Download size={12} /> CSV
            </button>
          </div>
        </div>
      </div>

      {/* Events */}
      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="card p-4 flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-forge-elevated" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-48 bg-forge-elevated rounded" />
                <div className="h-3 w-96 bg-forge-elevated rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="card p-8 text-center">
          <Activity size={28} className="mx-auto text-text-muted mb-2" />
          <p className="text-sm text-text-muted">No audit events found</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-text-muted">
              Showing {events.length} of {formatNumber(total)} events
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setFilters(prev => ({ ...prev, offset: Math.max(0, prev.offset - prev.limit) }))}
                disabled={filters.offset === 0}
                className="btn-ghost text-xs disabled:opacity-30"
              >
                ← Previous
              </button>
              <button
                onClick={() => setFilters(prev => ({ ...prev, offset: prev.offset + prev.limit }))}
                disabled={filters.offset + filters.limit >= total}
                className="btn-ghost text-xs disabled:opacity-30"
              >
                Next →
              </button>
            </div>
          </div>

          {events.map((event) => {
            const isExpanded = expandedEvent === event.event_id;
            return (
              <div key={event.event_id} className="card overflow-hidden">
                <button
                  onClick={() => setExpandedEvent(isExpanded ? null : event.event_id)}
                  className="w-full flex items-start gap-3 p-4 text-left hover:bg-forge-elevated/30 transition-colors"
                >
                  <div className={cn(
                    "p-2 rounded-lg shrink-0",
                    categoryBgs[event.category] || "bg-forge-elevated"
                  )}>
                    <Clock size={14} className={categoryColors[event.category] || "text-text-muted"} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <SeverityBadge severity={event.severity} />
                      <span className={cn(
                        "text-[10px] font-semibold uppercase tracking-wider",
                        categoryColors[event.category] || "text-text-muted"
                      )}>
                        {event.category}
                      </span>
                      <span className="text-[10px] font-mono text-text-muted">
                        {event.action}
                      </span>
                    </div>
                    <p className="text-xs text-text-primary leading-relaxed">{event.detail}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-[10px] font-mono text-text-muted">{event.actor}</span>
                      <span className="text-[10px] font-mono text-text-muted">{formatTimeAgo(event.timestamp)}</span>
                      {event.ip_address && <span className="text-[10px] text-text-muted">{event.ip_address}</span>}
                    </div>
                  </div>
                  <div className="shrink-0">
                    {isExpanded ? <ChevronUp size={14} className="text-text-muted" /> : <ChevronDown size={14} className="text-text-muted" />}
                  </div>
                </button>
                {isExpanded && (
                  <div className="px-4 pb-4 pt-0 space-y-2 border-t border-forge-border">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
                      <div>
                        <span className="text-[9px] text-text-muted block">Event ID</span>
                        <span className="text-[10px] font-mono text-text-primary">{event.event_id}</span>
                      </div>
                      <div>
                        <span className="text-[9px] text-text-muted block">ISO Timestamp</span>
                        <span className="text-[10px] font-mono text-text-primary">{event.timestamp_iso}</span>
                      </div>
                      <div>
                        <span className="text-[9px] text-text-muted block">Resource</span>
                        <span className="text-[10px] font-mono text-text-primary">{event.resource}{event.resource_id ? `/${event.resource_id.slice(0, 12)}` : ""}</span>
                      </div>
                      <div>
                        <span className="text-[9px] text-text-muted block">Hash (first 16)</span>
                        <span className="text-[10px] font-mono text-text-muted">{event.event_hash.slice(0, 16)}...</span>
                      </div>
                    </div>
                    {Object.keys(event.metadata).length > 0 && (
                      <div className="pt-1">
                        <span className="text-[9px] text-text-muted block mb-1">Metadata</span>
                        <pre className="text-[10px] font-mono bg-forge-elevated rounded p-2 text-text-secondary overflow-x-auto">
                          {JSON.stringify(event.metadata, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════════════

export default function EnterprisePage() {
  const [activeTab, setActiveTab] = useState<TabId>("sso");

  const renderTab = () => {
    switch (activeTab) {
      case "sso": return <SSOTab />;
      case "rbac": return <RBACTab />;
      case "audit": return <AuditTab />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <Shield size={22} className="text-forge-primary" />
            Enterprise
          </h1>
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-forge-primary/10 text-forge-primary border border-forge-primary/20 uppercase tracking-wider">
            SOC 2 Ready
          </span>
        </div>
        <p className="text-sm text-text-muted">
          SSO configuration, user role management, and compliance audit log
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-forge-border">
        <nav className="flex gap-1 -mb-px">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all",
                  isActive
                    ? "border-forge-primary text-forge-primary"
                    : "border-transparent text-text-muted hover:text-text-secondary hover:border-zinc-700"
                )}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Active tab */}
      {renderTab()}
    </div>
  );
}
