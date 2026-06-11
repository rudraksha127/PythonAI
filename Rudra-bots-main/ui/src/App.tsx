import { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SidebarProvider, useSidebar } from "@/lib/sidebar-context";
import Sidebar from "@/components/Sidebar";
import ChatArea from "@/components/ChatArea";
import ThemeModal from "@/components/ThemeModal";
import BrainModal from "@/components/BrainModal";
import { Dashboard, Settings } from "@/pages";

// ─── Shared layout: Sidebar + children ─────────────────────────

function MainLayout({ children }: { children: React.ReactNode }) {
  const sidebar = useSidebar();
  const [showTheme, setShowTheme] = useState(false);
  const [showBrain, setShowBrain] = useState(false);

  return (
    <div className="h-screen flex overflow-hidden">
      {sidebar.visible && (
        <Sidebar
          onToggle={() => sidebar.hide()}
          onOpenTheme={() => setShowTheme(true)}
          onOpenBrain={() => setShowBrain(true)}
        />
      )}
      {children}
      {showTheme && <ThemeModal onClose={() => setShowTheme(false)} />}
      {showBrain && <BrainModal onClose={() => setShowBrain(false)} />}
    </div>
  );
}

// ─── Chat page (default main view) ──────────────────────────────

function ChatPage() {
  const sidebar = useSidebar();
  return (
    <MainLayout>
      <ChatArea onToggleSidebar={() => sidebar.toggle()} />
    </MainLayout>
  );
}

// ─── Settings page ──────────────────────────────────────────────

function SettingsPage() {
  return (
    <MainLayout>
      <Settings />
    </MainLayout>
  );
}

// ─── Dashboard page ─────────────────────────────────────────────

function DashboardPage() {
  return (
    <MainLayout>
      <Dashboard />
    </MainLayout>
  );
}

// ─── Login page (no sidebar) ────────────────────────────────────

function LoginPage() {
  const [mode, setMode] = useState<"login" | "signup" | "setup">("login");

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative">
      <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 via-transparent to-cyan-500/5 pointer-events-none" />
      <div className="card p-8 w-full max-w-sm relative z-10 animate-fade-in">
        <div className="text-center mb-6">
          <div className="w-12 h-12 bg-[var(--accent)]/20 rounded-xl flex items-center justify-center mx-auto mb-3">
            <svg viewBox="0 0 32 32" className="w-6 h-6 text-[var(--accent)]" fill="currentColor">
              <path d="M16 4L16 22L6 22Z" />
              <path d="M16 8L16 22L24 22Z" opacity="0.6" />
              <path d="M4 24Q10 20 16 24Q22 28 28 24" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" />
            </svg>
          </div>
          <h1 className="text-xl font-bold bg-gradient-to-r from-[var(--accent)] to-[var(--accent)]/60 bg-clip-text text-transparent">
            Odysseus
          </h1>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            window.location.href = "/chat";
          }}
          className="space-y-4"
        >
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Username</label>
            <input type="text" required className="input" placeholder="Enter username" />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Password</label>
            <input type="password" required className="input" placeholder="Enter password" />
          </div>
          {mode !== "login" && (
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Confirm Password</label>
              <input type="password" required className="input" placeholder="Confirm password" />
            </div>
          )}
          <button type="submit" className="btn-primary w-full">
            {mode === "setup" ? "Create Admin Account" : mode === "signup" ? "Create Account" : "Sign In"}
          </button>
        </form>

        <div className="text-center mt-4">
          <button
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
            className="text-xs text-zinc-500 hover:text-[var(--accent)] transition-colors"
          >
            {mode === "login" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Components demo page ───────────────────────────────────────

function ComponentsDemo() {
  return (
    <div className="min-h-screen overflow-y-auto p-8">
      <div className="max-w-5xl mx-auto space-y-12">
        <div>
          <h1 className="text-3xl font-bold mb-2">Odysseus UI Components</h1>
          <p className="text-zinc-400">A modern component library for the Odysseus AI chat interface</p>
        </div>

        {/* Buttons */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">Buttons</h2>
          <div className="flex flex-wrap gap-3">
            <button className="btn-primary">Primary</button>
            <button className="btn-secondary">Secondary</button>
            <button className="btn-ghost">Ghost</button>
            <button className="btn-destructive">Destructive</button>
            <button className="btn-primary" disabled>Disabled</button>
          </div>
        </section>

        {/* Cards */}
        <section>
          <h2 className="text-lg font-semibold mb-4 pb-2 border-b">Cards</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card p-6">
              <h3 className="font-semibold mb-2">Card Title</h3>
              <p className="text-sm text-zinc-400 mb-4">
                A basic card component.
              </p>
              <div className="flex gap-2">
                <button className="btn-secondary text-xs">Cancel</button>
                <button className="btn-primary text-xs">Save</button>
              </div>
            </div>
          </div>
        </section>

        <div className="text-center text-xs text-zinc-600 pt-6 border-t">
          Odysseus UI Components v2.0
        </div>
      </div>
    </div>
  );
}

// ─── Root App ───────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <SidebarProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/components" element={<ComponentsDemo />} />
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </SidebarProvider>
    </BrowserRouter>
  );
}
