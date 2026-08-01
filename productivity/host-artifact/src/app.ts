import { constants } from "node:fs";
import { createHash } from "node:crypto";
import { lstat, open, readFile, readdir, realpath } from "node:fs/promises";
import path from "node:path";
import { Hono } from "hono";
import type { Context } from "hono";
import { getMimeType } from "hono/utils/mime";
import { ARTIFACT_NAME_PATTERN, HEALTH_PATH, PROTOCOL_VERSION, REVISION_HEADER, WORKSPACE_PATTERN } from "./config.js";
import { parseMetadata, type ArtifactMetadata } from "./publisher.js";

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);
}

async function currentMetadata(root: string, workspace: string, artifact: string): Promise<ArtifactMetadata | undefined> {
  try { return parseMetadata(JSON.parse(await readFile(path.join(root, "v2", "workspaces", workspace, "artifacts", artifact, "current.json"), "utf8"))); }
  catch { return undefined; }
}

async function shelf(root: string): Promise<ArtifactMetadata[]> {
  const found: ArtifactMetadata[] = [];
  const workspacesRoot = path.join(root, "v2", "workspaces");
  let workspaces: string[];
  try { workspaces = await readdir(workspacesRoot); } catch { return found; }
  for (const workspace of workspaces) {
    if (!WORKSPACE_PATTERN.test(workspace)) continue;
    let artifacts: string[];
    try { artifacts = await readdir(path.join(workspacesRoot, workspace, "artifacts")); } catch { continue; }
    for (const artifact of artifacts) {
      if (!ARTIFACT_NAME_PATTERN.test(artifact)) continue;
      const metadata = await currentMetadata(root, workspace, artifact);
      if (metadata && metadata.workspace === workspace && metadata.name === artifact) found.push(metadata);
    }
  }
  return found.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function createArtifactApp(options: { root: string }): Hono {
  const app = new Hono();
  app.get(HEALTH_PATH, (context) => context.json({ service: "host-artifact", version: PROTOCOL_VERSION, status: "ok" }));
  app.get("/", async (context) => {
    const entries = await shelf(path.resolve(options.root));
    const items = entries.map((entry) => `<li><a href="/a/${encodeURIComponent(entry.workspace)}/${encodeURIComponent(entry.name)}/">${escapeHtml(entry.name)}</a> <small>${escapeHtml(entry.workspace.split("~")[0]!)} · ${escapeHtml(entry.kind)} · <time>${escapeHtml(entry.updatedAt)}</time></small></li>`).join("");
    context.header("Cache-Control", "no-store");
    context.header("X-Content-Type-Options", "nosniff");
    return context.html(`<!doctype html><html><head><meta charset="utf-8"><title>Artifacts</title></head><body><h1>Artifacts</h1><ul>${items}</ul></body></html>`);
  });

  async function serve(context: Context) {
    const workspace = context.req.param("workspace") ?? "";
    const artifact = context.req.param("artifact") ?? "";
    if (!WORKSPACE_PATTERN.test(workspace) || !ARTIFACT_NAME_PATTERN.test(artifact)) return context.notFound();
    const metadata = await currentMetadata(path.resolve(options.root), workspace, artifact);
    if (!metadata || metadata.workspace !== workspace || metadata.name !== artifact) return context.notFound();
    const routePrefix = `/a/${workspace}/${artifact}/`;
    const wildcard = context.req.param("*");
    let requested: string;
    if (wildcard !== undefined) requested = wildcard || metadata.entry;
    else {
      const encoded = context.req.path.startsWith(routePrefix) ? context.req.path.slice(routePrefix.length) : "";
      try { requested = encoded ? decodeURIComponent(encoded) : metadata.entry; } catch { return context.notFound(); }
    }
    const segments = requested.split("/");
    if (!requested || segments.some((part) => !part || part === "." || part === ".." || part.startsWith("."))) return context.notFound();
    if (metadata.kind !== "directory" && requested !== metadata.entry) return context.notFound();
    const root = await realpath(path.resolve(options.root));
    const revisionRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", artifact, "revisions", metadata.revision);
    const candidate = path.join(revisionRoot, ...segments);
    try {
      const artifactRoot = path.join(root, "v2", "workspaces", workspace, "artifacts", artifact);
      if ((await lstat(artifactRoot)).isSymbolicLink() || (await lstat(revisionRoot)).isSymbolicLink()) return context.notFound();
      const resolvedArtifact = await realpath(artifactRoot);
      const resolvedRevision = await realpath(revisionRoot);
      if (!resolvedArtifact.startsWith(`${root}${path.sep}`) || !resolvedRevision.startsWith(`${resolvedArtifact}${path.sep}`)) return context.notFound();
      let prefix = revisionRoot;
      for (const segment of segments) { prefix = path.join(prefix, segment); if ((await lstat(prefix)).isSymbolicLink()) return context.notFound(); }
      const resolved = await realpath(candidate);
      if (!resolved.startsWith(`${resolvedRevision}${path.sep}`) || !resolved.startsWith(`${root}${path.sep}`)) return context.notFound();
      const handle = await open(candidate, constants.O_RDONLY | constants.O_NOFOLLOW);
      let body: Buffer;
      try { if (!(await handle.stat()).isFile()) return context.notFound(); body = await handle.readFile(); } finally { await handle.close(); }
      const etag = `"${createHash("sha256").update(body).digest("hex")}"`;
      context.header("Cache-Control", "no-store"); context.header("X-Content-Type-Options", "nosniff");
      context.header("Content-Type", getMimeType(resolved) ?? "application/octet-stream"); context.header("ETag", etag); context.header(REVISION_HEADER, metadata.revision);
      if (context.req.header("If-None-Match") === etag) return context.body(null, 304);
      return context.body(body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) as ArrayBuffer);
    } catch { return context.notFound(); }
  }
  app.get("/a/:workspace/:artifact", (context) => context.redirect(`${context.req.path}/`, 308));
  app.get("/a/:workspace/:artifact/*", serve);
  app.get("/a/:workspace/:artifact/", serve);
  app.notFound((context) => context.text("Not Found", 404));
  return app;
}
