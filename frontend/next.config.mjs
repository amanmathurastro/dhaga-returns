import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// The repo keeps one .env at the root (shared with the backend). Next.js only
// looks inside frontend/, so pick up the one public value we need from there.
// Nothing else from that file is read: backend secrets never enter this process.
if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
  try {
    const env = readFileSync(fileURLToPath(new URL("../.env", import.meta.url)), "utf8");
    const match = env.match(/^NEXT_PUBLIC_API_BASE_URL=([^#\n]*)/m);
    if (match && match[1].trim()) process.env.NEXT_PUBLIC_API_BASE_URL = match[1].trim();
  } catch {
    // No root .env (e.g. on a deploy host): the variable is set on the host, or the default applies.
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
  },
};

export default nextConfig;
