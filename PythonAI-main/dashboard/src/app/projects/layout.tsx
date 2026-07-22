import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Projects",
  description:
    "Manage your code projects, RAG indices, and trained adapters. Track training phases, language support, and indexing status.",
};

export default function ProjectsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
