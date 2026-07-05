import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/shell/Shell";

export const metadata: Metadata = {
  title: "Vantage — BTC/ETH Futures Paper Trading",
  description: "Risk-aware BTC/ETH futures analytics and paper trading on real market data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
