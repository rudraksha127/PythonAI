import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Progress",
  description:
    "Track ForgeAI development milestones, phase completion, test suite results, and architecture overview across the full pipeline.",
};

export default function ProgressLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
