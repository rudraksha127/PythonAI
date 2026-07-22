import { useState } from "react";
import { Palette, Bot, Server, Save, Check } from "lucide-react";

const MODELS = [
  { id: "claude-opus", name: "Claude Opus 4.5", provider: "Anthropic" },
  { id: "claude-sonnet", name: "Claude Sonnet 4", provider: "Anthropic" },
  { id: "gpt4o", name: "GPT-4o", provider: "OpenAI" },
  { id: "deepseek", name: "DeepSeek Coder", provider: "DeepSeek" },
  { id: "qwen", name: "Qwen 2.5 7B", provider: "Ollama (Local)" },
];

const THEMES = [
  { name: "Glass", bg: "#0f0c29", accent: "#a855f7" },
  { name: "Midnight", bg: "#0a0a0a", accent: "#6366f1" },
  { name: "Cyberpunk", bg: "#0d0221", accent: "#ff6b9d" },
  { name: "Forest", bg: "#0a1a0f", accent: "#34d399" },
  { name: "Ocean", bg: "#0a1628", accent: "#22d3ee" },
];

export default function Settings() {
  const [selectedModel, setSelectedModel] = useState(MODELS[0].id);
  const [selectedTheme, setSelectedTheme] = useState(THEMES[0].name);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-bold">Settings</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Configure your chat experience
        </p>
      </div>

      {/* Model Selection */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Bot size={16} className="text-purple-400" />
          <h2 className="text-sm font-semibold">Default Model</h2>
        </div>
        <div className="space-y-2">
          {MODELS.map((model) => (
            <button
              key={model.id}
              onClick={() => setSelectedModel(model.id)}
              className={`w-full flex items-center justify-between p-3 rounded-lg border transition-all ${
                selectedModel === model.id
                  ? "border-purple-500/50 bg-purple-500/10"
                  : "border-zinc-800 hover:border-zinc-700"
              }`}
            >
              <div>
                <div className="text-sm font-medium">{model.name}</div>
                <div className="text-[11px] text-zinc-500">{model.provider}</div>
              </div>
              {selectedModel === model.id && (
                <Check size={16} className="text-purple-400" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Theme Selection */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Palette size={16} className="text-purple-400" />
          <h2 className="text-sm font-semibold">Theme</h2>
        </div>
        <div className="grid grid-cols-5 gap-2">
          {THEMES.map((theme) => (
            <button
              key={theme.name}
              onClick={() => setSelectedTheme(theme.name)}
              className={`p-3 rounded-lg border text-center transition-all ${
                selectedTheme === theme.name
                  ? "border-purple-500/50"
                  : "border-zinc-800 hover:border-zinc-700"
              }`}
            >
              <div
                className="w-full h-8 rounded-md mb-1"
                style={{
                  background: `linear-gradient(135deg, ${theme.bg}, ${theme.accent}44)`,
                  borderLeft: `3px solid ${theme.accent}`,
                }}
              />
              <div className="text-[10px] text-zinc-400">{theme.name}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Server Info */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Server size={16} className="text-purple-400" />
          <h2 className="text-sm font-semibold">Server Connection</h2>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">API Endpoint</span>
            <span className="font-mono text-xs text-zinc-300">/api</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-zinc-400">Status</span>
            <span className="flex items-center gap-1 text-green-400">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              Connected
            </span>
          </div>
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end">
        <button onClick={handleSave} className="btn-primary">
          {saved ? (
            <>
              <Check size={14} />
              Saved
            </>
          ) : (
            <>
              <Save size={14} />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  );
}
