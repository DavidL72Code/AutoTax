import type { NextConfig } from "next";

/* One service in production, two processes in development.

   `next build` exports the whole interface to static HTML and JavaScript that
   calls `/api/...` relatively, and the FastAPI app serves those files itself.
   That makes the deployment a single origin: no second host to configure, no
   CORS, no cross-site cookie problem, and no proxy hop in front of the progress
   stream. The backend's address is never sent to a browser because there is no
   separate backend address.

   In development the two run apart, so `next dev` forwards /api to BACKEND_URL
   instead. Rewrites do not exist in an export, hence the split. */
const isDev = process.env.NODE_ENV === "development";
const backend = process.env.BACKEND_URL ?? "http://localhost:8020";

const nextConfig: NextConfig = isDev
  ? {
      /* gzip buffers a server-sent event stream: the proxy would compress the
         sync progress feed, `EventSource` would open and then stay silent, and
         curl would hide it by not asking for compression. */
      compress: false,
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
      },
    }
  : {
      output: "export",
      images: { unoptimized: true },
    };

export default nextConfig;
