import type { Metadata, Viewport } from "next";
import { Be_Vietnam_Pro, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// Be Vietnam Pro is drawn for Vietnamese diacritics (stacked tone marks stay legible at 13–14px).
const sans = Be_Vietnam_Pro({
  variable: "--font-be-vietnam",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const mono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "FreshMesh · Trợ lý quyết định hàng tươi",
  description: "Dự báo, nhập hàng, xử lý tồn và giao hàng cho chuỗi mini-mart, mỗi số liệu ghi rõ nguồn dữ liệu.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eaefec" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1310" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
