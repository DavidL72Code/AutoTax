import type { NextConfig } from "next";

/* The browser talks to this app's own origin, and this app forwards to the
   API. Nothing about the backend's address is compiled into the bundle.

   That matters for three reasons beyond tidiness:

   * A same-origin request carries the session cookie. A frontend on one domain
     calling an API on another does not, because the cookie is `samesite=lax`,
     so a split deployment would look configured and silently fail to sign in.
   * There is no cross-origin request, so there is no CORS to configure.
   * `BACKEND_URL` has no `NEXT_PUBLIC_` prefix, so it stays server-side. The
     old `NEXT_PUBLIC_API_BASE` was baked into the JavaScript sent to visitors,
     which meant a missing value shipped `http://localhost:8010` to every
     browser and failed only at runtime, after a green build.

   `NEXT_PUBLIC_API_BASE` still overrides it, for pointing a local frontend
   straight at a remote API. */
const backend = process.env.BACKEND_URL ?? "http://localhost:8020";

const nextConfig: NextConfig = {
  /* The sync progress stream is server-sent events, and gzip buffers: the proxy
     compressed the stream, nothing reached the browser until enough bytes
     accumulated, and `EventSource` sat open and silent forever. curl hid it,
     because curl does not ask for compression unless told to.

     Compression is the CDN's job in front of this app anyway; these payloads
     are small JSON and HTML that Vercel already serves compressed. */
  compress: false,

  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
