import type { NextConfig } from "next";

/**
 * Static export, deliberately.
 *
 * The whole application is one container on one port: FastAPI serves `out/`
 * underneath the API routers (R3), so there is no Node process in production
 * and no second origin to configure CORS for. Anything requiring a Next server
 * at runtime — server actions, ISR, `next/image` optimisation, route handlers —
 * is therefore unavailable by construction, not by preference.
 */
const nextConfig: NextConfig = {
  output: "export",
};

export default nextConfig;
