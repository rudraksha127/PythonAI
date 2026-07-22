import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Settings",
  description:
    "Configure inference backends, training parameters, system preferences, and API keys for the ForgeAI platform.",
};

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
