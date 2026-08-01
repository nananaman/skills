#!/usr/bin/env bun
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { artifactRoute, DEFAULT_PORT, DEFAULT_PUBLISH_ROOT, HEALTH_PATH } from "./config.js";
import { ensureReady, isExpectedHealth, parseWorkspaceResult, selectTransport, waitForRevision } from "./cli-lib.js";
import { publishArtifact, removeArtifact } from "./publisher.js";
const exec = promisify(execFile); const origin = `http://127.0.0.1:${DEFAULT_PORT}`;
async function helper(command: string, args: string[]): Promise<unknown> { const { stdout } = await exec(command, args); return JSON.parse(stdout); }
async function healthy(): Promise<boolean> { try { const response = await fetch(`${origin}${HEALTH_PATH}`, { signal: AbortSignal.timeout(1000) }); return isExpectedHealth(response.status, await response.json()); } catch { return false; } }
async function ready(): Promise<void> { await ensureReady({ isHealthy: healthy, ensureService: async () => { await exec("host-artifact-service", ["ensure"]); } }); }
async function workspace() { return parseWorkspaceResult(await helper("host-artifact-workspace", ["resolve"])); }
async function main(): Promise<void> {
  const args = process.argv.slice(2); const command = args.shift();
  if (command === "publish") {
    const input = args.shift(); const nameIndex = args.indexOf("--name"); const name = nameIndex >= 0 ? args[nameIndex + 1] : undefined;
    if (!input || !name || args.length !== 2 || nameIndex !== 0) throw new Error("usage: host-artifact publish PATH --name NAME");
    await ready(); const ws = await workspace();
    const published = await publishArtifact(input, { root: DEFAULT_PUBLISH_ROOT, workspace: ws.segment, name, verify: async (candidate) => { if (!(await waitForRevision(`${origin}${candidate.route}`, candidate.revision))) throw new Error("published revision is not reachable from localhost"); } });
    const localUrl = `${origin}${published.route}`;
    let inspect: unknown; try { inspect = await helper("host-artifact-tailscale", ["inspect"]); } catch { inspect = undefined; }
    let verification: unknown;
    if (typeof inspect === "object" && inspect !== null && (inspect as Record<string, unknown>).configured === true) { try { verification = await helper("host-artifact-tailscale", ["verify", ws.segment, name, published.revision]); } catch (error) { verification = { schemaVersion: 1, verified: false, reason: error instanceof Error ? error.message : String(error) }; } }
    const transport = selectTransport(localUrl, inspect, verification);
    process.stdout.write(`${JSON.stringify({ schemaVersion: 1, workspace: ws, name, revision: published.revision, url: transport.url, transport: transport.transport, kind: published.kind, updatedAt: published.updatedAt, ...(transport.reason ? { remoteUnavailable: transport.reason } : {}) })}\n`); return;
  }
  if (command === "remove") { if (args[0] !== "--name" || !args[1] || args.length !== 2) throw new Error("usage: host-artifact remove --name NAME"); const ws = await workspace(); await removeArtifact({ root: DEFAULT_PUBLISH_ROOT, workspace: ws.segment, name: args[1] }); process.stdout.write(`${JSON.stringify({ schemaVersion: 1, removed: { workspace: ws.segment, name: args[1] } })}\n`); return; }
  if (command === "status") { if (args.length) throw new Error("usage: host-artifact status"); const ok = await healthy(); let inspect: unknown; try { inspect = await helper("host-artifact-tailscale", ["inspect"]); } catch {} process.stdout.write(`${JSON.stringify({ schemaVersion: 1, healthy: ok, localOrigin: origin, tailscale: inspect })}\n`); if (!ok) process.exitCode = 1; return; }
  if (command === "setup") { if (args.length) throw new Error("usage: host-artifact setup"); await ready(); process.stdout.write(`${JSON.stringify(await helper("host-artifact-tailscale", ["setup"]))}\n`); return; }
  throw new Error("usage: host-artifact <publish PATH --name NAME | remove --name NAME | status | setup>");
}
main().catch((error) => { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; });
