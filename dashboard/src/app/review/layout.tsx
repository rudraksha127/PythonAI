import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Code Review",
  description: "AI-powered code review — analyze code quality, security, and best practices",
};

export default function ReviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
