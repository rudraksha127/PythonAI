import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Model Battle Arena",
  description: "Compare LLM providers side-by-side — latency, cost, and quality metrics",
};

export default function BattleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
