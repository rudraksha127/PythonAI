"use client";

import React, { useEffect, useState } from "react";
// Custom local UI components styled with the ForgeAI design system
const Card = ({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={`card-hover p-6 ${className || ""}`} {...props}>{children}</div>
);
const CardHeader = ({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={`mb-4 flex flex-row items-center justify-between ${className || ""}`} {...props}>{children}</div>
);
const CardTitle = ({ className, children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h3 className={`text-base font-semibold text-text-primary ${className || ""}`} {...props}>{children}</h3>
);
const CardContent = ({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={`${className || ""}`} {...props}>{children}</div>
);
const Badge = ({ variant, className, children, ...props }: { variant?: string; className?: string; children: React.ReactNode }) => {
  const badgeClass = variant === "outline" ? "border border-zinc-700 text-text-muted" : "bg-forge-primary/10 text-forge-primary";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${badgeClass} ${className || ""}`} {...props}>
      {children}
    </span>
  );
};
const ScrollArea = ({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={`overflow-y-auto pr-2 ${className || ""}`} {...props}>{children}</div>
);

// Simple tooltip implementation using CSS relative positioning
const Tooltip = ({ children }: { children: React.ReactNode }) => (
  <div className="relative group inline-block">{children}</div>
);
const TooltipTrigger = ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) => (
  <>{children}</>
);
const TooltipContent = ({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={`absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 hidden group-hover:block z-50 bg-forge-surface border border-forge-border rounded-lg p-3 text-xs shadow-2xl min-w-[160px] pointer-events-none transition-all duration-200 ${className || ""}`} {...props}>
    {children}
  </div>
);

// API Helper – pulls from the new FastAPI endpoint
async function fetchArsenalInventory() {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";
  const resp = await fetch(`${apiBase}/api/arsenal/inventory`);
  if (!resp.ok) throw new Error("Failed to fetch arsenal inventory");
  return resp.json();
}

export default function ArsenalDashboard() {
  const [inventory, setInventory] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchArsenalInventory()
      .then((data) => setInventory(data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[70vh]">
        <div className="text-muted-foreground">Loading Arsenal inventory…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-red-600">Error: {error}</div>
    );
  }

  const { total_categories, total_tools, categories } = inventory;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-6 flex items-center">
        <span className="mr-2">🧰 Arsenal Repository Index</span>
        <Badge variant="secondary">{total_tools} tools</Badge>
      </h1>

      <Card className="mb-6 shadow-lg">
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Overall Summary</span>
            <Badge variant="outline">{total_categories} categories</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatItem label="Tools" value={total_tools} />
          <StatItem label="Categories" value={total_categories} />
          <StatItem label="Git repos" value={inventory.stats.git_repos} />
          <StatItem label="Readmes" value={inventory.stats.with_readme} />
        </CardContent>
      </Card>

      <ScrollArea className="h-[60vh] border rounded-md">
        <div className="space-y-6 p-4">
          {categories.map((cat: any) => (
            <CategoryCard key={cat.id} category={cat} />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center">
      <span className="text-xl font-medium">{value}</span>
      <span className="text-sm text-muted-foreground">{label}</span>
    </div>
  );
}

function CategoryCard({ category }: { category: any }) {
  return (
    <Card className="shadow-md hover:shadow-xl transition-shadow">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{category.name}</CardTitle>
        <Badge variant="secondary">{category.tool_count} tools</Badge>
      </CardHeader>
      <CardContent>
        <ul className="list-disc list-inside space-y-1 text-sm">
          {category.tools.map((tool: any) => (
            <li key={tool.name} className="flex items-center">
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="cursor-help underline decoration-dotted">
                    {tool.name}
                  </span>
                </TooltipTrigger>
                <TooltipContent side="right" className="max-w-xs">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <span className="font-medium">Lang:</span>
                    <span>{tool.language}</span>
                    <span className="font-medium">Git:</span>
                    <span>{tool.has_git ? "✔" : "✘"}</span>
                    <span className="font-medium">Readme:</span>
                    <span>{tool.has_readme ? "✔" : "✘"}</span>
                    <span className="font-medium">Size:</span>
                    <span>{tool.size_mb} MB</span>
                  </div>
                </TooltipContent>
              </Tooltip>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
