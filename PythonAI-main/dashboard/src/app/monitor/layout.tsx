import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Monitor",
  description:
    "Real-time monitoring dashboard — WebSocket live console, multi-agent swarm status, RAG pipeline health, and API provider metrics.",
};

export default function MonitorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
