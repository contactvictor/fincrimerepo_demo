import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "FinCrime Balance Migration & Reconciliation Platform",
  description: "Automated migration reconciliation, exception management and audit evidence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
