import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL
  ? process.env.NEXT_PUBLIC_SITE_URL
  : process.env.VERCEL_URL
  ? `https://${process.env.VERCEL_URL}`
  : "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "Radar",
  description: "Recently funded startups before they post jobs.",
  icons: {
    icon: "/favicon.svg",
    apple: "/apple-icon",
  },
  openGraph: {
    title: "Radar",
    description: "Recently funded startups before they post jobs.",
    type: "website",
    url: siteUrl,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {children}
        <footer className="mt-auto border-t border-border px-[12vw] py-5 text-xs text-muted-foreground text-right">
          <Link
            href="/philosophy"
            className="underline underline-offset-2 hover:text-foreground transition-colors"
          >
            Philosophy
          </Link>
          <span className="mx-2 text-muted-foreground/50">·</span>
          built by{" "}
          <a
            href="https://www.linkedin.com/in/samarv/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-foreground transition-colors"
          >
            Samar Varma
          </a>
        </footer>
        <Analytics />
      </body>
    </html>
  );
}
