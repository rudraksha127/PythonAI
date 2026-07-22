import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent",
  description:
    "Chat with the ForgeAI coding agent. Get AI-assisted code generation, debugging, and explanation using your project's RAG context.",
};

export default function AgentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
