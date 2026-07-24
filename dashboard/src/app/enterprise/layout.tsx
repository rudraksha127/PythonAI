import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Enterprise",
  description:
    "SSO configuration, role-based access control, and compliance audit log for ForgeAI Enterprise.",
};

export default function EnterpriseLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
