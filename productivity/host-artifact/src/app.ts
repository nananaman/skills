import { constants } from "node:fs";
import { createHash } from "node:crypto";
import { lstat, open, realpath } from "node:fs/promises";
import path from "node:path";
import { Hono } from "hono";
import { getMimeType } from "hono/utils/mime";
import { ARTIFACT_ID_PATTERN, HEALTH_PATH, type Exposure } from "./config.js";

export function createArtifactApp(options: {
  root: string;
  exposure?: Exposure;
  tailscaleState?: () => { ready: boolean; address?: string };
}): Hono {
  const app = new Hono();
  app.get(HEALTH_PATH, (context) => {
    const tailscale = options.tailscaleState?.();
    return context.json({
      service: "host-artifact",
      version: 1,
      status: "ok",
      ...(tailscale ? {
        tailscaleReady: tailscale.ready,
        ...(tailscale.address ? { tailscaleAddress: tailscale.address } : {}),
      } : {}),
    });
  });
  app.get("/:id/*", async (context) => {
    const id = context.req.param("id");
    if (!ARTIFACT_ID_PATTERN.test(id)) return context.notFound();
    if (options.exposure === "tailscale" && !id.startsWith("tailscale-")) return context.notFound();
    let requested: string;
    try {
      requested = decodeURIComponent(context.req.path.slice(id.length + 2));
    } catch {
      return context.notFound();
    }
    const segments = requested.split("/");
    if (!requested || segments.some((part) => !part || part === "." || part === ".." || part.startsWith("."))) {
      return context.notFound();
    }
    const root = path.resolve(options.root);
    const artifactRoot = path.join(root, id);
    const candidate = path.join(artifactRoot, ...segments);
    try {
      if ((await lstat(artifactRoot)).isSymbolicLink()) return context.notFound();
      let prefix = artifactRoot;
      for (const segment of segments) {
        prefix = path.join(prefix, segment);
        if ((await lstat(prefix)).isSymbolicLink()) return context.notFound();
      }
      const resolvedArtifact = await realpath(artifactRoot);
      const resolved = await realpath(candidate);
      const resolvedRoot = await realpath(root);
      if (!resolvedArtifact.startsWith(`${resolvedRoot}${path.sep}`) || !resolved.startsWith(`${resolvedArtifact}${path.sep}`)) return context.notFound();
      const handle = await open(candidate, constants.O_RDONLY | constants.O_NOFOLLOW);
      let body: Buffer;
      try {
        if (!(await handle.stat()).isFile()) return context.notFound();
        body = await handle.readFile();
      } finally {
        await handle.close();
      }
      context.header("Cache-Control", "no-store");
      context.header("X-Content-Type-Options", "nosniff");
      context.header("Content-Type", getMimeType(resolved) ?? "application/octet-stream");
      const etag = `"${createHash("sha256").update(body).digest("hex")}"`;
      context.header("ETag", etag);
      if (context.req.header("If-None-Match") === etag) return context.body(null, 304);
      const arrayBuffer = body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) as ArrayBuffer;
      return context.body(arrayBuffer);
    } catch {
      return context.notFound();
    }
  });
  app.notFound((context) => context.text("Not Found", 404));
  return app;
}
