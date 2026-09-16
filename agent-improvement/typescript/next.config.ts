import type { NextConfig } from "next";

// Mock external services only — no pages. The agent + evals run as tsx
// scripts on the host (see src/, db/, Makefile).
const nextConfig: NextConfig = {};

export default nextConfig;
