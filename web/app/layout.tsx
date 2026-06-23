import type { Metadata } from "next";
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

export const metadata: Metadata = {
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
        <footer className="mt-auto border-t border-border px-[12vw] py-5 text-xs text-muted-foreground flex justify-end">
          <span>built by </span>
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
