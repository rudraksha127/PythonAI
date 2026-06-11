"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Brain,
  GitBranch,
  Bot,
  Settings,
  Activity,
  Menu,
  X,
  Zap,
  Cpu,
  Layers,
} from "lucide-react";
import { useState } from "react";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/progress", label: "Progress", icon: Activity },
  { href: "/monitor", label: "Monitor", icon: Cpu },
  { href: "/training", label: "Training", icon: Layers },
  { href: "/seal", label: "SEAL", icon: Brain },
  { href: "/projects", label: "Projects", icon: GitBranch },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed top-4 left-4 z-50 lg:hidden btn-ghost p-2"
        aria-label="Toggle navigation"
      >
        {isOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-30 lg:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed top-0 left-0 z-40 h-full w-64 glass border-r border-forge-border",
          "flex flex-col",
          "transition-transform duration-200 lg:translate-x-0",
          isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-forge-border">
          <div className="w-8 h-8 rounded-lg bg-forge-primary/20 flex items-center justify-center">
            <Zap size={18} className="text-forge-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-text-primary">ForgeAI</h1>
            <p className="text-[11px] text-text-muted">Self-Improving AI</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsOpen(false)}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
                  isActive
                    ? "text-forge-primary bg-forge-primary/10"
                    : "text-text-secondary hover:text-text-primary hover:bg-forge-elevated"
                )}
              >
                <Icon size={18} className={isActive ? "text-forge-primary" : ""} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div className="px-3 py-4 border-t border-forge-border">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
            <span className="text-xs text-text-muted">Server connected</span>
          </div>
          <Link
            href="https://codebuff.com"
            target="_blank"
            className="flex items-center gap-2 px-3 py-2 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <Brain size={14} />
            Powered by ForgeAI v2.0
          </Link>
        </div>
      </aside>
    </>
  );
}
