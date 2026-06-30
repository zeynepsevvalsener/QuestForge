import type { Metadata } from "next";

import { Providers } from "@/lib/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuestForge",
  description: "An AI Game Master for a text-adventure RPG.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
