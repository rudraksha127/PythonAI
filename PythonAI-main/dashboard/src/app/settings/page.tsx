"use client";

import { useState } from "react";
import {
  Settings,
  Bot,
  Brain,
  Server,
  Key,
  Save,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  Eye,
  EyeOff,
  Zap,
  Database,
  Bell,
} from "lucide-react";

// ─── Tab Config ─────────────────────────────────────────────────

const TABS = [
  { id: "model", label: "Model", icon: Bot },
  { id: "training", label: "Training", icon: Brain },
  { id: "system", label: "System", icon: Server },
  { id: "api-keys", label: "API Keys", icon: Key },
] as const;

type TabId = (typeof TABS)[number]["id"];

// ─── Section Component ──────────────────────────────────────────

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-5 mb-4">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        {description && (
          <p className="text-xs text-text-muted mt-1">{description}</p>
        )}
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

// ─── Field Component ────────────────────────────────────────────

function Field({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <label className="block text-sm font-medium text-text-primary">
          {label}
        </label>
        {description && (
          <p className="text-xs text-text-muted mt-0.5">{description}</p>
        )}
      </div>
      <div className="shrink-0 w-[200px]">{children}</div>
    </div>
  );
}

// ─── Toggle Component ───────────────────────────────────────────

function Toggle({
  enabled,
  onChange,
  label,
}: {
  enabled: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-6 w-10 items-center rounded-full transition-colors ${
        enabled ? "bg-forge-primary" : "bg-zinc-700"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
          enabled ? "translate-x-5" : "translate-x-1"
        }`}
      />
      {label && (
        <span className="ml-3 text-sm text-text-secondary">{label}</span>
      )}
    </button>
  );
}

// ─── Model Settings Tab ─────────────────────────────────────────

function ModelSettings() {
  const [backend, setBackend] = useState("ollama");
  const [model, setModel] = useState("qwen2.5-coder:14b");
  const [url, setUrl] = useState("http://localhost:11434");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [temperature, setTemperature] = useState("0.7");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div>
      <SettingsSection
        title="Inference Backend"
        description="Choose the inference engine for code generation and agent responses."
      >
        <Field label="Backend" description="Engine used for model inference">
          <select
            value={backend}
            onChange={(e) => setBackend(e.target.value)}
            className="input text-sm"
          >
            <option value="ollama">Ollama (Local)</option>
            <option value="openai">OpenAI (Cloud)</option>
            <option value="anthropic">Anthropic (Cloud)</option>
            <option value="vllm">vLLM (Local, Power)</option>
            <option value="sglang">SGLang (Local, Max)</option>
          </select>
        </Field>

        <Field label="Model" description="Default model identifier">
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="input text-sm font-mono"
          />
        </Field>

        <Field label="Server URL" description="Inference endpoint URL">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="input text-sm font-mono"
          />
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Generation Parameters"
        description="Defaults for code generation requests."
      >
        <Field
          label="Max Tokens"
          description="Maximum response length in tokens"
        >
          <input
            type="number"
            value={maxTokens}
            onChange={(e) => setMaxTokens(e.target.value)}
            className="input text-sm font-mono"
            min={256}
            max={32768}
          />
        </Field>

        <Field
          label="Temperature"
          description="Randomness (0 = deterministic, 1 = creative)"
        >
          <div className="flex items-center gap-3">
            <input
              type="range"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              min="0"
              max="1"
              step="0.05"
              className="flex-1 accent-forge-primary"
            />
            <span className="text-sm font-mono text-text-primary w-10 text-right">
              {temperature}
            </span>
          </div>
        </Field>
      </SettingsSection>

      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary gap-2">
          {saved ? (
            <>
              <CheckCircle2 size={16} />
              Saved
            </>
          ) : (
            <>
              <Save size={16} />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Training Settings Tab ──────────────────────────────────────

function TrainingSettings() {
  const [schedule, setSchedule] = useState("weekly");
  const [scheduleDay, setScheduleDay] = useState("sunday");
  const [scheduleTime, setScheduleTime] = useState("02:00");
  const [minExamples, setMinExamples] = useState("50");
  const [phase, setPhase] = useState("1");
  const [syntheticAug, setSyntheticAug] = useState(true);
  const [sdftEnabled, setSdftEnabled] = useState(true);
  const [rollbackEnabled, setRollbackEnabled] = useState(true);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div>
      <SettingsSection
        title="Schedule"
        description="Automated training cadence for model improvement."
      >
        <Field label="Frequency" description="How often training runs">
          <select
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            className="input text-sm"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="biweekly">Bi-weekly</option>
            <option value="manual">Manual only</option>
          </select>
        </Field>

        {schedule === "weekly" && (
          <>
            <Field label="Day" description="Day of the week">
              <select
                value={scheduleDay}
                onChange={(e) => setScheduleDay(e.target.value)}
                className="input text-sm"
              >
                <option value="sunday">Sunday</option>
                <option value="monday">Monday</option>
                <option value="tuesday">Tuesday</option>
                <option value="wednesday">Wednesday</option>
                <option value="thursday">Thursday</option>
                <option value="friday">Friday</option>
                <option value="saturday">Saturday</option>
              </select>
            </Field>
          </>
        )}

        <Field label="Time" description="Time of day (24h)">
          <input
            type="time"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
            className="input text-sm font-mono"
          />
        </Field>

        <Field
          label="Min Examples"
          description="Minimum signals required to trigger training"
        >
          <input
            type="number"
            value={minExamples}
            onChange={(e) => setMinExamples(e.target.value)}
            className="input text-sm font-mono"
            min={10}
            max={10000}
          />
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Training Phase"
        description="Current training approach for model improvement."
      >
        <Field
          label="Phase"
          description="Training algorithm (changes require restart)"
        >
          <select
            value={phase}
            onChange={(e) => setPhase(e.target.value)}
            className="input text-sm"
          >
            <option value="1">Phase 1 — QLoRA (SFT)</option>
            <option value="2">Phase 2 — GRPO (RL)</option>
            <option value="3">Phase 3 — SEAL (Dual-Loop)</option>
          </select>
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Advanced"
        description="Additional training pipeline options."
      >
        <Field label="Synthetic Augmentation">
          <Toggle
            enabled={syntheticAug}
            onChange={setSyntheticAug}
          />
        </Field>

        <Field label="SDFT Replay Buffer">
          <Toggle
            enabled={sdftEnabled}
            onChange={setSdftEnabled}
          />
        </Field>

        <Field label="Rollback Guard">
          <Toggle
            enabled={rollbackEnabled}
            onChange={setRollbackEnabled}
          />
        </Field>
      </SettingsSection>

      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary gap-2">
          {saved ? (
            <>
              <CheckCircle2 size={16} />
              Saved
            </>
          ) : (
            <>
              <Save size={16} />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── System Settings Tab ────────────────────────────────────────

function SystemSettings() {
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("7337");
  const [logLevel, setLogLevel] = useState("INFO");
  const [telemetry, setTelemetry] = useState(false);
  const [realtime, setRealtime] = useState(true);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div>
      <SettingsSection
        title="Server"
        description="ForgeAI local server configuration."
      >
        <Field label="Host" description="Bind address">
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            className="input text-sm font-mono"
          />
        </Field>

        <Field label="Port" description="API server port">
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(e.target.value)}
            className="input text-sm font-mono"
            min={1024}
            max={65535}
          />
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Logging"
        description="System observability configuration."
      >
        <Field label="Log Level" description="Verbosity of server logs">
          <select
            value={logLevel}
            onChange={(e) => setLogLevel(e.target.value)}
            className="input text-sm"
          >
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </Field>
      </SettingsSection>

      <SettingsSection
        title="Privacy"
        description="Data collection and transmission controls."
      >
        <Field
          label="Telemetry"
          description="Share anonymous usage metrics (acceptance rate only)"
        >
          <Toggle
            enabled={telemetry}
            onChange={setTelemetry}
          />
        </Field>

        <Field label="Realtime Updates">
          <Toggle
            enabled={realtime}
            onChange={setRealtime}
          />
        </Field>
      </SettingsSection>

      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary gap-2">
          {saved ? (
            <>
              <CheckCircle2 size={16} />
              Saved
            </>
          ) : (
            <>
              <Save size={16} />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── API Keys Settings Tab ──────────────────────────────────────

function ApiKeysSettings() {
  const [keys, setKeys] = useState<Record<string, string>>({
    openai: "",
    anthropic: "",
    groq: "",
  });
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState(false);

  const handleChange = (provider: string, value: string) => {
    setKeys((prev) => ({ ...prev, [provider]: value }));
  };

  const toggleVisibility = (provider: string) => {
    setVisibleKeys((prev) => ({ ...prev, [provider]: !prev[provider] }));
  };

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const providers = [
    { id: "openai", label: "OpenAI", envVar: "OPENAI_API_KEY" },
    { id: "anthropic", label: "Anthropic", envVar: "ANTHROPIC_API_KEY" },
    { id: "groq", label: "Groq", envVar: "GROQ_API_KEY" },
  ];

  return (
    <div>
      <SettingsSection
        title="Provider API Keys"
        description="API keys for cloud inference providers. Stored locally in your OS keychain."
      >
        {providers.map((provider) => (
          <Field
            key={provider.id}
            label={provider.label}
            description={`Env: ${provider.envVar}`}
          >
            <div className="relative">
              <input
                type={visibleKeys[provider.id] ? "text" : "password"}
                value={keys[provider.id]}
                onChange={(e) => handleChange(provider.id, e.target.value)}
                placeholder="sk-..."
                className="input text-sm font-mono pr-9"
              />
              <button
                onClick={() => toggleVisibility(provider.id)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
              >
                {visibleKeys[provider.id] ? (
                  <EyeOff size={14} />
                ) : (
                  <Eye size={14} />
                )}
              </button>
            </div>
          </Field>
        ))}
      </SettingsSection>

      <SettingsSection
        title="Environment Variables"
        description="All supported env vars for configuring ForgeAI."
      >
        <div className="space-y-1.5 text-xs">
          {[
            { var: "FORGEAI_MODEL", desc: "Default inference model" },
            { var: "FORGEAI_INFERENCE_BACKEND", desc: "Backend engine" },
            { var: "FORGEAI_LOG_LEVEL", desc: "Logging verbosity" },
            { var: "FORGEAI_BASE_MODEL", desc: "Training base model" },
            { var: "FORGEAI_CLOUD_ENABLED", desc: "Enable cloud features" },
            { var: "FORGEAI_ALLOW_SIGNUPS", desc: "Allow self-registration" },
            { var: "SUPABASE_URL", desc: "Supabase project URL" },
            { var: "STRIPE_SECRET_KEY", desc: "Stripe API secret" },
          ].map((env) => (
            <div
              key={env.var}
              className="flex items-center gap-3 py-1.5 text-text-secondary"
            >
              <span className="font-mono text-text-primary text-[11px] w-44 shrink-0">
                {env.var}
              </span>
              <span className="text-text-muted">{env.desc}</span>
            </div>
          ))}
        </div>
      </SettingsSection>

      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary gap-2">
          {saved ? (
            <>
              <CheckCircle2 size={16} />
              Saved
            </>
          ) : (
            <>
              <Save size={16} />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("model");

  const renderTab = () => {
    switch (activeTab) {
      case "model":
        return <ModelSettings />;
      case "training":
        return <TrainingSettings />;
      case "system":
        return <SystemSettings />;
      case "api-keys":
        return <ApiKeysSettings />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="text-sm text-text-muted mt-1">
          Configure inference, training, system preferences, and API keys.
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
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
                  isActive
                    ? "border-forge-primary text-forge-primary"
                    : "border-transparent text-text-muted hover:text-text-secondary hover:border-zinc-700"
                }`}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Active tab content */}
      {renderTab()}
    </div>
  );
}
