import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VARSHA Weather AI - Decision-Support Dashboard",
  description:
    "Verified Adaptive Regime-aware Skill-weighted Hybrid Analytics (SIH26081). " +
    "Decision-Support Prototype - Synthetic Development Dataset - " +
    "Not an Official Weather Warning.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}