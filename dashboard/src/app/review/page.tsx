"use client";

import { useState, useRef } from "react";
import {
  Code,
  FileCode,
  GitBranch,
  Upload,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Lightbulb,
  ThumbsUp,
  TrendingUp,
  Search,
  Loader2,
  Download,
  Copy,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────

interface ReviewIssue {
  line: number | null;
  column: number | null;
  severity: "critical" | "error" | "warning" | "info" | "style";
  category: string;
  message: string;
  suggestion: string | null;
  code_snippet: string | null;
}

interface ReviewResult {
  file_path: string | null;
  summary: string;
  score: number;
  issues: ReviewIssue[];
  strengths: string[];
  suggestions: string[];
  language: string;
}

interface GitChange {
  file_path: string;
  change_type: string;
  language: string;
  additions: number;
  deletions: number;
}

// ─── API ─────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";

async function reviewCode(code: string, language: string, filePath?: string) {
  const res = await fetch(`${API_BASE}/api/review/code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, language, file_path: filePath }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json();
}

async function reviewGit(staged: boolean, commitRange?: string) {
  const res = await fetch(`${API_BASE}/api/review/git`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ staged, commit_range: commitRange }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json();
}

// ─── Severity Badge ─────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const config: Record<string, { icon: React.ElementType; color: string; bg: string }> = {
    critical: { icon: XCircle, color: "text-error", bg: "bg-error/10" },
    error: { icon: AlertTriangle, color: "text-warning", bg: "bg-warning/10" },
    warning: { icon: AlertTriangle, color: "text-[#f59e0b]", bg: "bg-[#f59e0b]/10" },
    info: { icon: Info, color: "text-forge-primary", bg: "bg-forge-primary/10" },
    style: { icon: Info, color: "text-text-muted", bg: "bg-forge-elevated" },
  };
  const c = config[severity] || config.info;
  const Icon = c.icon;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${c.color} ${c.bg}`}>
      <Icon size={10} />
      {severity}
    </span>
  );
}

// ─── Score Ring ─────────────────────────────────────────────────

function ScoreRing({ score }: { score: number }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(score / 10, 1);
  const color = score >= 8 ? "#22c55e" : score >= 6 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative w-20 h-20 flex items-center justify-center">
      <svg className="w-20 h-20 -rotate-90" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={radius} fill="none" stroke="#27272C" strokeWidth="4" />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <span className="absolute text-xl font-bold" style={{ color }}>
        {score.toFixed(1)}
      </span>
    </div>
  );
}

// ─── Issue Card ─────────────────────────────────────────────────

function IssueCard({ issue, index }: { issue: ReviewIssue; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-forge-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-forge-elevated/50 transition-colors"
      >
        <div className="mt-0.5 shrink-0">
          {expanded ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono text-text-muted">#{index + 1}</span>
            <SeverityBadge severity={issue.severity} />
            <span className="text-[10px] font-mono text-text-muted uppercase">{issue.category.replace(/_/g, " ")}</span>
            {issue.line && <span className="text-[10px] font-mono text-text-muted">L{issue.line}</span>}
          </div>
          <p className="text-sm text-text-primary leading-relaxed">{issue.message}</p>
        </div>
      </button>
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-forge-border pt-2">
          {issue.suggestion && (
            <div className="flex items-start gap-2">
              <Lightbulb size={14} className="text-warning mt-0.5 shrink-0" />
              <p className="text-xs text-text-secondary">{issue.suggestion}</p>
            </div>
          )}
          {issue.code_snippet && (
            <pre className="text-xs font-mono bg-forge-elevated rounded-lg p-2 overflow-x-auto text-text-secondary">
              {issue.code_snippet}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Review Result Panel ────────────────────────────────────────

function ReviewResultPanel({ result }: { result: ReviewResult }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = JSON.stringify(result, null, 2);
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `review-${result.file_path?.replace(/\//g, "-") || "code"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const criticalCount = result.issues.filter((i) => i.severity === "critical").length;
  const errorCount = result.issues.filter((i) => i.severity === "error").length;
  const warningCount = result.issues.filter((i) => i.severity === "warning").length;

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* Header stats */}
      <div className="card p-5">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">Review Results</h3>
            {result.file_path && (
              <p className="text-xs font-mono text-text-muted mt-1">{result.file_path}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleCopy} className="btn-ghost p-2" title="Copy results">
              {copied ? <CheckCircle2 size={14} className="text-success" /> : <Copy size={14} />}
            </button>
            <button onClick={handleDownload} className="btn-ghost p-2" title="Download results">
              <Download size={14} />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <ScoreRing score={result.score} />
          <div className="flex gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-error">{criticalCount}</div>
              <div className="text-[10px] text-text-muted uppercase">Critical</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-warning">{errorCount}</div>
              <div className="text-[10px] text-text-muted uppercase">Errors</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-[#f59e0b]">{warningCount}</div>
              <div className="text-[10px] text-text-muted uppercase">Warnings</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-text-primary">{result.issues.length}</div>
              <div className="text-[10px] text-text-muted uppercase">Total</div>
            </div>
          </div>
        </div>

        <p className="text-sm text-text-secondary mt-4 leading-relaxed">{result.summary}</p>
      </div>

      {/* Issues */}
      {result.issues.length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-text-primary mb-3">
            Issues ({result.issues.length})
          </h3>
          <div className="space-y-2">
            {result.issues.map((issue, i) => (
              <IssueCard key={i} issue={issue} index={i} />
            ))}
          </div>
        </div>
      )}

      {/* Strengths */}
      {result.strengths.length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <ThumbsUp size={14} className="text-success" />
            Strengths
          </h3>
          <ul className="space-y-2">
            {result.strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckCircle2 size={14} className="text-success mt-0.5 shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggestions */}
      {result.suggestions.length > 0 && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
            <Lightbulb size={14} className="text-warning" />
            Suggestions
          </h3>
          <ul className="space-y-2">
            {result.suggestions.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <TrendingUp size={14} className="text-forge-primary mt-0.5 shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Git Review Results ─────────────────────────────────────────

function GitReviewResults({ data }: { data: { reviews: ReviewResult[]; overall_score: number; summary: string; total_issues: number; critical_count: number; error_count: number } }) {
  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* Overall stats */}
      <div className="card p-5">
        <div className="flex items-center gap-6 mb-4">
          <ScoreRing score={data.overall_score} />
          <div className="flex gap-6">
            <div className="text-center">
              <div className="text-2xl font-bold text-text-primary">{data.reviews.length}</div>
              <div className="text-[10px] text-text-muted uppercase">Files</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-error">{data.critical_count}</div>
              <div className="text-[10px] text-text-muted uppercase">Critical</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-warning">{data.error_count}</div>
              <div className="text-[10px] text-text-muted uppercase">Errors</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-text-primary">{data.total_issues}</div>
              <div className="text-[10px] text-text-muted uppercase">Issues</div>
            </div>
          </div>
        </div>
        <p className="text-sm text-text-secondary">{data.summary}</p>
      </div>

      {/* Per-file reviews */}
      {data.reviews.map((review, i) => (
        <ReviewResultPanel key={i} result={review} />
      ))}
    </div>
  );
}

// ─── Language selector ──────────────────────────────────────────

const LANGUAGES = [
  { id: "python", label: "Python" },
  { id: "javascript", label: "JavaScript" },
  { id: "typescript", label: "TypeScript" },
  { id: "go", label: "Go" },
  { id: "rust", label: "Rust" },
  { id: "java", label: "Java" },
  { id: "cpp", label: "C++" },
  { id: "csharp", label: "C#" },
  { id: "ruby", label: "Ruby" },
  { id: "php", label: "PHP" },
  { id: "swift", label: "Swift" },
  { id: "kotlin", label: "Kotlin" },
];

// ─── Main Page ──────────────────────────────────────────────────

export default function ReviewPage() {
  const [activeTab, setActiveTab] = useState<"code" | "git">("code");
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("python");
  const [filePath, setFilePath] = useState("");
  const [fileInput, setFileInput] = useState<File | null>(null);
  const [staged, setStaged] = useState(false);
  const [commitRange, setCommitRange] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileInput(file);
    setFilePath(file.name);

    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    const extToLang: Record<string, string> = {
      py: "python", js: "javascript", ts: "typescript", jsx: "javascript",
      tsx: "typescript", go: "go", rs: "rust", java: "java", rb: "ruby",
      cpp: "cpp", c: "c", cs: "csharp", swift: "swift", kt: "kotlin",
      php: "php", scala: "scala",
    };
    if (extToLang[ext]) setLanguage(extToLang[ext]);

    const reader = new FileReader();
    reader.onload = (event) => {
      setCode(event.target?.result as string || "");
    };
    reader.readAsText(file);
  };

  const handlePasteSample = () => {
    setCode(`def calculate_average(numbers):
    total = sum(numbers)
    count = len(numbers)
    return total / count

def process_user_data(data):
    # TODO: implement validation
    result = {}
    for key, value in data.items():
        try:
            result[key] = complex_calculation(value)
        except:
            pass
    return result

def authenticate(username, password):
    API_KEY = "sk-1234567890"
    if username == "admin":
        return True
    return False`);
    setLanguage("python");
    setFilePath("sample.py");
  };

  const handleReview = async () => {
    setError(null);
    setResult(null);

    if (activeTab === "code") {
      if (!code.trim()) {
        setError("Please enter or paste some code to review.");
        return;
      }
      setLoading(true);
      try {
        const data = await reviewCode(code, language, filePath || undefined);
        if (data.success) {
          setResult({
            type: "code",
            data: {
              file_path: data.file_path,
              summary: data.summary,
              score: data.score,
              issues: data.issues,
              strengths: data.strengths,
              suggestions: data.suggestions,
              language: data.language,
            } as ReviewResult,
          });
        } else {
          setError(data.error || "Review failed");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to review code");
      } finally {
        setLoading(false);
      }
    } else {
      setLoading(true);
      try {
        const data = await reviewGit(staged, commitRange || undefined);
        if (data.success) {
          setResult({
            type: "git",
            data,
          });
        } else {
          setError(data.error || "Git review failed");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to review git changes");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Code Review</h1>
        <p className="text-sm text-text-muted mt-1">
          AI-powered code review — analyze code quality, security, and best practices.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-forge-elevated rounded-lg w-fit">
        <button
          onClick={() => { setActiveTab("code"); setResult(null); setError(null); }}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
            activeTab === "code"
              ? "bg-forge-primary/20 text-forge-primary"
              : "text-text-muted hover:text-text-primary"
          }`}
        >
          <FileCode size={16} />
          Code Review
        </button>
        <button
          onClick={() => { setActiveTab("git"); setResult(null); setError(null); }}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
            activeTab === "git"
              ? "bg-forge-primary/20 text-forge-primary"
              : "text-text-muted hover:text-text-primary"
          }`}
        >
          <GitBranch size={16} />
          Git Changes
        </button>
      </div>

      {/* Input area */}
      <div className="card p-5">
        {activeTab === "code" ? (
          <div className="space-y-4">
            {/* File upload + language */}
            <div className="flex items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="hidden"
                accept=".py,.js,.ts,.jsx,.tsx,.go,.rs,.java,.rb,.cpp,.c,.cs,.swift,.kt,.php,.scala"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="btn-secondary text-xs gap-1.5"
              >
                <Upload size={14} />
                {fileInput ? fileInput.name : "Choose File"}
              </button>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="input text-xs py-2 w-32"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.id} value={l.id}>{l.label}</option>
                ))}
              </select>
              <button
                onClick={handlePasteSample}
                className="btn-ghost text-xs"
              >
                Load Sample
              </button>
              {filePath && (
                <span className="text-xs text-text-muted ml-auto">{filePath}</span>
              )}
            </div>

            {/* Code textarea */}
            <textarea
              ref={textareaRef}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Paste your code here for review..."
              rows={12}
              className="input resize-none font-mono text-sm w-full"
              spellCheck={false}
            />
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-text-secondary">
              Review uncommitted git changes in the current repository.
            </p>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={staged}
                  onChange={(e) => setStaged(e.target.checked)}
                  className="rounded border-forge-border bg-forge-elevated text-forge-primary focus:ring-forge-primary"
                />
                <span className="text-sm text-text-secondary">Staged changes only</span>
              </label>
              <div className="flex-1" />
              <input
                type="text"
                value={commitRange}
                onChange={(e) => setCommitRange(e.target.value)}
                placeholder="Commit range (e.g. HEAD~3..HEAD)"
                className="input text-xs py-2 w-64"
              />
            </div>
            <div className="bg-forge-elevated rounded-lg p-4">
              <p className="text-xs text-text-muted">
                <Code size={12} className="inline mr-1" />
                This will run <code className="text-forge-primary">git diff</code> on the current repository
                and review all changed files.
              </p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-4 p-3 rounded-lg bg-error/10 border border-error/20 text-sm text-error">
            <AlertTriangle size={14} className="inline mr-1.5" />
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center justify-between mt-4">
          <button
            onClick={handleReview}
            disabled={loading}
            className="btn-primary gap-2"
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Reviewing...
              </>
            ) : (
              <>
                <Search size={16} />
                {activeTab === "code" ? "Review Code" : "Review Changes"}
              </>
            )}
          </button>
          {result && (
            <button
              onClick={() => { setResult(null); setError(null); }}
              className="btn-ghost text-xs"
            >
              Clear Results
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {loading && (
        <div className="card p-12 flex flex-col items-center justify-center">
          <Loader2 size={32} className="text-forge-primary animate-spin mb-4" />
          <p className="text-sm text-text-muted">Analyzing code with AI...</p>
        </div>
      )}

      {result && !loading && (
        <div>
          {result.type === "code" ? (
            <ReviewResultPanel result={result.data} />
          ) : (
            <GitReviewResults data={result.data} />
          )}
        </div>
      )}
    </div>
  );
}
