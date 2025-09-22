// next.config.mjs

const boaBase = process.env.NEXT_PUBLIC_BOA_BASE_URL || 'http://35.190.197.221';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produce .next/standalone for slimmer Docker images
  output: 'standalone',

  reactStrictMode: true,
  poweredByHeader: false,

  // Make the BoA base URL available in client code at build time
  env: {
    NEXT_PUBLIC_BOA_BASE_URL: boaBase,
  },

  // Optional: enable a local/dev proxy so /bank/* goes to BoA.
  // Turn on by setting ENABLE_BANK_REWRITE=1 at build/run time.
  async rewrites() {
    if (process.env.ENABLE_BANK_REWRITE === '1') {
      return [
        {
          source: '/bank/:path*',
          destination: `${boaBase}/:path*`,
        },
      ];
    }
    return [];
  },

  // Hackathon-friendly: don’t fail builds on lint/TS checks
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
};

export default nextConfig;
