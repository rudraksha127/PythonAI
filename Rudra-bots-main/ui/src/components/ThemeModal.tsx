import { X, Sun, Moon, Palette, Type, Layout } from "lucide-react";
import { useState } from "react";

interface ThemeModalProps {
  onClose: () => void;
}

const themes = [
  { name: "Glass", colors: ["#0f0c29", "#302b63", "#24243e"], accent: "#a855f7" },
  { name: "Midnight", colors: ["#0a0a0a", "#1a1a2e", "#16213e"], accent: "#6366f1" },
  { name: "Cyberpunk", colors: ["#0d0221", "#150734", "#1a0a3e"], accent: "#ff6b9d" },
  { name: "Forest", colors: ["#0a1a0f", "#0f2a18", "#1a3a22"], accent: "#34d399" },
  { name: "Ocean", colors: ["#0a1628", "#0f2140", "#1a2d52"], accent: "#22d3ee" },
  { name: "Terminal", colors: ["#0a0a0a", "#111111", "#1a1a1a"], accent: "#50fa7b" },
];

export default function ThemeModal({ onClose }: ThemeModalProps) {
  const [activeTab, setActiveTab] = useState<"themes" | "customize">("themes");
  const [bgColor, setBgColor] = useState("#0f0c29");
  const [accentColor, setAccentColor] = useState("#a855f7");

  const applyTheme = (theme: (typeof themes)[0]) => {
    setBgColor(theme.colors[0]);
    setAccentColor(theme.accent);
    document.documentElement.style.setProperty("--bg", theme.colors[0]);
    document.documentElement.style.setProperty("--accent", theme.accent);
    // Update body background
    document.body.style.background = `linear-gradient(135deg, ${theme.colors[0]} 0%, ${theme.colors[1]} 50%, ${theme.colors[2]} 100%)`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative glass border border-[var(--border)] rounded-xl w-full max-w-lg max-h-[80vh] overflow-y-auto animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Palette size={16} className="text-[var(--accent)]" />
            <h2 className="text-sm font-semibold">Theme</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--panel)] transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--border)]">
          {["themes", "customize"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as typeof activeTab)}
              className={`flex-1 text-xs font-medium py-3 transition-colors ${
                activeTab === tab
                  ? "text-[var(--accent)] border-b-2 border-[var(--accent)]"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab === "themes" ? (
                <span className="flex items-center justify-center gap-1">
                  <Palette size={12} /> Themes
                </span>
              ) : (
                <span className="flex items-center justify-center gap-1">
                  <Layout size={12} /> Customize
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-4">
          {activeTab === "themes" ? (
            <div className="grid grid-cols-3 gap-3">
              {themes.map((theme) => (
                <button
                  key={theme.name}
                  onClick={() => applyTheme(theme)}
                  className="card p-3 text-center hover:border-[var(--accent)]/50 transition-all group"
                >
                  <div className="flex gap-1 justify-center mb-2">
                    {theme.colors.map((c, i) => (
                      <div
                        key={i}
                        className="w-4 h-4 rounded-full border border-white/10"
                        style={{ background: c }}
                      />
                    ))}
                  </div>
                  <div
                    className="w-2 h-2 rounded-full mx-auto mb-1"
                    style={{ background: theme.accent }}
                  />
                  <div className="text-xs text-zinc-400 group-hover:text-[var(--fg)] transition-colors">
                    {theme.name}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-2">Background</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={bgColor}
                    onChange={(e) => {
                      setBgColor(e.target.value);
                      document.documentElement.style.setProperty("--bg", e.target.value);
                    }}
                    className="w-10 h-10 rounded cursor-pointer border border-[var(--border)] bg-transparent"
                  />
                  <span className="text-xs font-mono text-zinc-500">{bgColor}</span>
                </div>
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-2">Accent Color</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={accentColor}
                    onChange={(e) => {
                      setAccentColor(e.target.value);
                      document.documentElement.style.setProperty("--accent", e.target.value);
                    }}
                    className="w-10 h-10 rounded cursor-pointer border border-[var(--border)] bg-transparent"
                  />
                  <span className="text-xs font-mono text-zinc-500">{accentColor}</span>
                </div>
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-2">Font</label>
                <select className="input text-xs">
                  <option>System UI (Default)</option>
                  <option>Monospace</option>
                  <option>Sans-serif</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-2">Density</label>
                <select className="input text-xs">
                  <option>Comfortable</option>
                  <option>Compact</option>
                  <option>Spacious</option>
                </select>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
