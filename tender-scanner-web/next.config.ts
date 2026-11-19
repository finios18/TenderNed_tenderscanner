import type { NextConfig } from "next";
const config: NextConfig = {
  distDir: process.env.NEXT_TEST_DIST_DIR || ".next",
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};
export default config;
