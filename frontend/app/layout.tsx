import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Providers from "./providers";
import "./globals.css";
// Dark theme for syntax-highlighted code blocks inside markdown.
import "highlight.js/styles/github-dark.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DocChat — B2B RAG Assistant",
  description: "Ask questions about your internal documents",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} h-full antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
