import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Returns Insight · Dhaga & Co.",
  description: "Which vendors are driving returns, and why.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main>{children}</main>
        <footer className="footer">
          Internal tool. It shows patterns in return comments; it does not decide anything or contact anyone.
        </footer>
      </body>
    </html>
  );
}
