import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // the page reads clip summaries from disk at request time; ship them with the server bundle
  outputFileTracingIncludes: { "/*": ["./public/clips/**/summary.json"] },
};

export default nextConfig;
