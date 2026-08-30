import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { AppState } from "@/components/AppState";
import { Shell } from "@/components/Shell";
import { THEME_SCRIPT, ThemeProvider } from "@/components/Theme";
import { I18nProvider } from "@/lib/i18n";

/* Same three faces v1 loaded: Inter for text, IBM Plex Mono for every number,
   Space Grotesk for headings. */
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const mono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });
const display = Space_Grotesk({ variable: "--font-grotesk", subsets: ["latin"], weight: ["500", "700"] });

export const metadata: Metadata = {
  title: "ReceiptAuto",
  description: "Turns receipt email into a spending ledger you can check.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${inter.variable} ${mono.variable} ${display.variable}`}>
        <ThemeProvider>
          <I18nProvider>
            <AppState>
              <Shell>{children}</Shell>
            </AppState>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
