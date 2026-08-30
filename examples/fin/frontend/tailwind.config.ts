import type { Config } from "tailwindcss";

/**
 * The palette lives here, once.
 *
 * Spec §2 names five colours; scattering them as hex literals across a dozen
 * components is how a "dark theme" ends up with four slightly different greys.
 * Components reference `bg-terminal`, `text-accent-yellow` and so on, so the
 * theme is one edit rather than a search-and-replace.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Spec §2 "Visual Design": backgrounds around #0d1117 / #1a1a2e, muted
        // grey borders, no pure black.
        terminal: {
          bg: "#0d1117",
          panel: "#1a1a2e",
          border: "#30363d",
          muted: "#8b949e",
          text: "#e6edf3",
        },
        // Spec §2 "Color Scheme".
        accent: {
          yellow: "#ecad0a",
          blue: "#209dd7",
          purple: "#753991",
        },
        // Price direction. Not in the spec's list, but the spec requires green
        // uptick / red downtick flashes, and those two need to be tokens for
        // the same reason the rest are.
        up: "#26a65b",
        down: "#e5484d",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
