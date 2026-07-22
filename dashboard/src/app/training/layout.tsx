import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Training",
  description:
    "Monitor training runs, track acceptance rate improvements, and trigger manual QLoRA/GRPO/SEAL fine-tuning for your ForgeAI models.",
};

export default function TrainingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
