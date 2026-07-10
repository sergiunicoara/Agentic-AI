import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartOps — Unified Observability",
  description: "AI-Powered Infrastructure Observability Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="bg-gray-950 text-gray-100 antialiased">
      <body>{children}</body>
    </html>
  );
}
