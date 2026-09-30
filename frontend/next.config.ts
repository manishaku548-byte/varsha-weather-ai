import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The repository root's parent folder contains an unrelated package-lock.json;
  // pin file tracing to the frontend folder so the build output stays clean.
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;