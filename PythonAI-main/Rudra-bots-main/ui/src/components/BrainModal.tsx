import { X, Brain, Sparkles, Plus, Search } from "lucide-react";
import { useState } from "react";

interface BrainModalProps {
  onClose: () => void;
}

const sampleMemories = [
  { text: "User prefers concise, bullet-point responses", category: "preferences", uses: 12 },
  { text: "Working on a React + TypeScript project", category: "context", uses: 8 },
  { text: "User is a senior full-stack developer", category: "profile", uses: 5 },
  { text: "Prefers functional components over class components", category: "preferences", uses: 7 },
  { text: "Uses pnpm as package manager", category: "tools", uses: 3 },
];

export default function BrainModal({ onClose }: BrainModalProps) {
  const [activeTab, setActiveTab] = useState<"memories" | "skills" | "add">("memories");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredMemories = sampleMemories.filter((m) =>
    m.text.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative glass border border-[var(--border)] rounded-xl w-full max-w-xl max-h-[85vh] overflow-hidden animate-fade-in flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Brain size={16} className="text-[var(--accent)]" />
            <h2 className="text-sm font-semibold">Brain</h2>
            <span className="text-[10px] text-zinc-500 font-mono">{sampleMemories.length}</span>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--panel)] transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-2 border-b border-[var(--border)]">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder="Search memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="input pl-8 text-xs"
            />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--border)]">
          {["memories", "skills", "add"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as typeof activeTab)}
              className={`flex-1 text-xs font-medium py-2.5 transition-colors ${
                activeTab === tab
                  ? "text-[var(--accent)] border-b-2 border-[var(--accent)]"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab === "memories" ? "Memories" : tab === "skills" ? "Skills" : "Add"}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === "memories" && (
            <div className="space-y-2">
              {filteredMemories.length === 0 ? (
                <div className="text-center py-8">
                  <Brain size={24} className="mx-auto text-zinc-600 mb-2" />
                  <p className="text-xs text-zinc-500">No memories found</p>
                </div>
              ) : (
                filteredMemories.map((memory, i) => (
                  <div
                    key={i}
                    className="card p-3 hover:border-[var(--accent)]/30 transition-all group"
                  >
                    <p className="text-xs text-[var(--fg)] mb-2">{memory.text}</p>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent)]/10 text-[var(--accent)]">
                        {memory.category}
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        {memory.uses} uses
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "skills" && (
            <div className="text-center py-8">
              <Sparkles size={24} className="mx-auto text-zinc-600 mb-2" />
              <p className="text-xs text-zinc-500">No skills yet. Skills help the AI follow reusable procedures.</p>
              <button
                onClick={() => setActiveTab("add")}
                className="btn-primary text-xs mt-3"
              >
                <Plus size={12} />
                Add Skill
              </button>
            </div>
          )}

          {activeTab === "add" && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Add a Memory</label>
                <textarea
                  className="input text-xs resize-none"
                  rows={3}
                  placeholder="e.g. 'I prefer concise replies'"
                />
                <div className="flex justify-end mt-2">
                  <button className="btn-primary text-xs">Add Memory</button>
                </div>
              </div>

              <div className="border-t border-[var(--border)] pt-4">
                <label className="block text-xs text-zinc-400 mb-1">Add a Skill</label>
                <input type="text" className="input text-xs mb-2" placeholder="Skill title" />
                <textarea
                  className="input text-xs resize-none mb-2"
                  rows={2}
                  placeholder="What problem does this skill solve?"
                />
                <textarea
                  className="input text-xs resize-none mb-2"
                  rows={2}
                  placeholder="The approach, steps, or rules"
                />
                <input type="text" className="input text-xs mb-3" placeholder="Tags (comma-separated)" />
                <div className="flex justify-end">
                  <button className="btn-primary text-xs">
                    <Plus size={12} />
                    Add Skill
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
