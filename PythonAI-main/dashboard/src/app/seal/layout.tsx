import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SEAL Self-Improvement",
  description:
    "SEAL Phase 3 — Autonomous curriculum generation, inner loop training, meta-learning, and cycle history.",
};

export default function SealLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
