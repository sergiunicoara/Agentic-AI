import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@smartops/shared-types"],
};

export default nextConfig;
