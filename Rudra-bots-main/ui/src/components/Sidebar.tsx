import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { MessageSquare, Search, Plus, Settings, Brain, Palette, Calendar, BookOpen, Image, ListTodo, Mail, Library, ChevronLeft, Sparkles, LayoutDashboard, BarChart3 } from "lucide-react";

interface SidebarProps {
  onToggle: () => void;
  onOpenTheme: () => void;
  onOpenBrain: () => void;
}

export default function Sidebar({ onToggle, onOpenTheme, onOpenBrain }: SidebarProps) {
  const location = useLocation();
  const [activeSession, setActiveSession] = useState("1");
  const [activeTab, setActiveTab] = useState("chats");

  const sessions = [
    { id: "1", title: "Building the React component", model: "Claude Opus 4", time: "2m ago" },
    { id: "2", title: "API design discussion", model: "GPT-4o", time: "15m ago" },
    { id: "3", title: "Debugging WebSocket connection", model: "Claude Sonnet", time: "1h ago" },
    { id: "4", title: "SQL query optimization", model: "DeepSeek Coder", time: "3h ago" },
    { id: "5", title: "Architecture review", model: "Claude Opus 4", time: "1d ago" },
    { id: "6", title: "Code review feedback", model: "GPT-4o", time: "2d ago" },
    { id: "7", title: "Testing strategy", model: "Claude Sonnet", time: "3d ago" },
    { id: "8", title: "Deployment pipeline setup", model: "Mistral Large", time: "5d ago" },
  ];

  const models = [
    { name: "Claude Opus 4.5", provider: "Anthropic", status: "online" },
    { name: "Claude Sonnet 4", provider: "Anthropic", status: "online" },
    { name: "GPT-4o", provider: "OpenAI", status: "online" },
    { name: "DeepSeek Coder", provider: "DeepSeek", status: "online" },
    { name: "Qwen 2.5 7B", provider: "Ollama", status: "offline" },
  ];

  const tools = [
    { id: "brain", label: "Brain", icon: Brain, action: onOpenBrain },
    { id: "calendar", label: "Calendar", icon: Calendar },
    { id: "cookbook", label: "Cookbook", icon: BookOpen },
    { id: "gallery", label: "Gallery", icon: Image },
    { id: "tasks", label: "Tasks", icon: ListTodo },
    { id: "email", label: "Email", icon: Mail },
    { id: "library", label: "Library", icon: Library },
  ];

  const isActivePath = (path: string) => location.pathname === path;

  return (
    <aside className="w-60 glass border-r border-[var(--border)] flex flex-col flex-shrink-0 h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-[var(--accent)]" />
          <span className="text-sm font-semibold text-[var(--accent)]">Odysseus</span>
        </div>
        <button
          onClick={onToggle}
          className="p-1 rounded hover:bg-[var(--panel)] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* Navigation */}
      <div className="px-3 py-2 space-y-0.5 border-b border-[var(--border)]">
        <Link
          to="/chat"
          className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors ${
            isActivePath("/chat")
              ? "text-[var(--accent)] bg-[var(--accent)]/10"
              : "text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)]"
          }`}
        >
          <MessageSquare size={14} />
          Chat
        </Link>
        <Link
          to="/dashboard"
          className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors ${
            isActivePath("/dashboard")
              ? "text-[var(--accent)] bg-[var(--accent)]/10"
              : "text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)]"
          }`}
        >
          <LayoutDashboard size={14} />
          Dashboard
        </Link>
        <Link
          to="/forgeai"
          className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors ${
            isActivePath("/forgeai")
              ? "text-[var(--accent)] bg-[var(--accent)]/10"
              : "text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)]"
          }`}
        >
          <BarChart3 size={14} />
          ForgeAI
        </Link>
        <Link
          to="/settings"
          className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors ${
            isActivePath("/settings")
              ? "text-[var(--accent)] bg-[var(--accent)]/10"
              : "text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)]"
          }`}
        >
          <Settings size={14} />
          Settings
        </Link>
      </div>

      {/* Actions */}
      <div className="px-3 py-2 space-y-1 border-b border-[var(--border)]">
        <button className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)] transition-colors">
          <Plus size={14} />
          New Chat
        </button>
        <button className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)] transition-colors">
          <Search size={14} />
          Search
        </button>
      </div>

      {/* Content tabs */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex border-b border-[var(--border)]">
          {["chats", "models"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 text-[10px] font-medium py-2 transition-colors ${
                activeTab === tab
                  ? "text-[var(--accent)] border-b-2 border-[var(--accent)]"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab === "chats" ? "Chats" : "Models"}
            </button>
          ))}
        </div>

        {activeTab === "chats" ? (
          <div className="py-1">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => setActiveSession(session.id)}
                className={`w-full text-left px-3 py-2 transition-colors ${
                  activeSession === session.id
                    ? "bg-[var(--accent)]/10 border-l-2 border-[var(--accent)]"
                    : "hover:bg-[var(--panel)]"
                }`}
              >
                <div className="text-xs font-medium truncate text-[var(--fg)]">
                  {session.title}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-zinc-500">{session.model}</span>
                  <span className="text-[10px] text-zinc-600">·</span>
                  <span className="text-[10px] text-zinc-500">{session.time}</span>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="py-1">
            {models.map((model) => (
              <div
                key={model.name}
                className="flex items-center gap-2 px-3 py-2 hover:bg-[var(--panel)] transition-colors"
              >
                <div
                  className={`w-1.5 h-1.5 rounded-full ${
                    model.status === "online" ? "bg-green-400 shadow-green-400/50" : "bg-zinc-600"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium truncate">{model.name}</div>
                  <div className="text-[10px] text-zinc-500">{model.provider}</div>
                </div>
                <button className="text-[10px] text-zinc-500 hover:text-[var(--accent)] px-1 py-0.5 rounded transition-colors">
                  +Chat
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tools Section */}
      <div className="border-t border-[var(--border)] px-3 py-2">
        <div className="text-[10px] text-zinc-600 font-medium uppercase tracking-wider mb-1 px-1">
          Tools
        </div>
        <div className="space-y-0.5">
          {tools.map((tool) => (
            <button
              key={tool.id}
              onClick={tool.action || (() => {})}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)] transition-colors"
            >
              <tool.icon size={14} className="opacity-50" />
              {tool.label}
            </button>
          ))}
        </div>
      </div>

      {/* User Bar */}
      <div className="border-t border-[var(--border)] px-3 py-2 flex items-center justify-between">
        <Link
          to="/login"
          className="flex items-center gap-2 hover:opacity-80 transition-opacity"
        >
          <div className="w-6 h-6 rounded-full bg-zinc-700 flex items-center justify-center text-[10px] font-medium">
            U
          </div>
          <span className="text-xs text-zinc-400">User</span>
        </Link>
        <Link
          to="/settings"
          className={`p-1 rounded transition-colors ${
            isActivePath("/settings")
              ? "text-[var(--accent)] bg-[var(--accent)]/10"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-[var(--panel)]"
          }`}
        >
          <Settings size={14} />
        </Link>
      </div>
    </aside>
  );
}
