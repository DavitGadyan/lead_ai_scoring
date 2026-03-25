import "./globals.css";
import type { ReactNode } from "react";
import { Inter, Manrope } from "next/font/google";

import { ThemeToggle } from "../components/theme-toggle";
import { ThemeProvider } from "../components/theme-provider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap"
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-heading",
  display: "swap"
});

export const metadata = {
  title: "LeadScore AI",
  description: "AI-powered lead scoring platform with n8n and Kubernetes deployment modes."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${manrope.variable}`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <main className="page">
            <nav className="nav-shell">
              <div className="nav-brand">
                <span className="nav-brand__badge">LS</span>
                <div>
                  <div className="nav-brand__title">LeadScore AI</div>
                  <div className="nav-brand__subtitle">Intelligence Workspace</div>
                </div>
              </div>
              <ThemeToggle />
            </nav>
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
