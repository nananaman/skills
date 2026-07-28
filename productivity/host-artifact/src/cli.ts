#!/usr/bin/env bun
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import {
  buildArtifactUrl,
  ensureReady,
  getReadyTailscaleAddress,
  hasReadyTailscaleListener,
  isExpectedHealth,
  publishVerified,
  waitForArtifact,
} from "./cli-lib.js";
import { DEFAULT_PORT, DEFAULT_PUBLISH_ROOT, HEALTH_PATH } from "./config.js";
import { hostArtifact, removeArtifact, updateArtifact } from "./publisher.js";

const execFileAsync = promisify(execFile);
const base = `http://127.0.0.1:${DEFAULT_PORT}`;

async function isHealthy(): Promise<boolean> {
  try {
    const response = await fetch(`${base}${HEALTH_PATH}`, { signal: AbortSignal.timeout(1_000) });
    return isExpectedHealth(response.status, await response.json());
  } catch {
    return false;
  }
}

async function ensureService(): Promise<void> {
  await execFileAsync("host-artifact-service", ["ensure"]);
}

const artifactWaitDependencies = {
  fetchStatus: async (url: string) => (await fetch(url, { signal: AbortSignal.timeout(1_000) })).status,
  wait: async (milliseconds: number) => new Promise<void>((resolve) => setTimeout(resolve, milliseconds)),
};

async function readyTailscaleAddress(): Promise<string | undefined> {
  let address: string | undefined;
  await waitForArtifact(`${base}${HEALTH_PATH}`, {
    ...artifactWaitDependencies,
    fetchStatus: async (url: string) => {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      const body = await response.json();
      address = getReadyTailscaleAddress(response.status, body);
      return hasReadyTailscaleListener(response.status, body) ? 200 : 503;
    },
  });
  return address;
}

async function verifiedUrls(
  id: string,
  relativePath: string,
  exposeToTailscale: boolean,
): Promise<{ urls: { localhost: string; tailscale?: string }; tailscaleUnavailable?: string }> {
  const localhost = buildArtifactUrl(base, id, relativePath);
  if (!(await waitForArtifact(localhost, artifactWaitDependencies))) {
    throw new Error("published artifact is not reachable from localhost; verify the service publish root");
  }
  const result: { urls: { localhost: string; tailscale?: string }; tailscaleUnavailable?: string } = {
    urls: { localhost },
  };
  const tailscale = exposeToTailscale ? await readyTailscaleAddress() : undefined;
  if (exposeToTailscale && !tailscale) {
    result.tailscaleUnavailable = "Tailscale IPv4 is unavailable";
  } else if (tailscale) {
    const remote = buildArtifactUrl(`http://${tailscale}:${DEFAULT_PORT}`, id, relativePath);
    result.urls.tailscale = remote;
  }
  return result;
}

async function main(): Promise<void> {
  const [command, value, ...flags] = process.argv.slice(2);
  if (command === "host" && value) {
    const exposeToTailscale = flags.includes("--tailscale");
    const liveReload = !flags.includes("--no-reload");
    if (flags.some((flag) => flag !== "--tailscale" && flag !== "--no-reload")) {
      throw new Error("unknown host option");
    }
    await ensureReady({ isHealthy, ensureService });
    const published = await publishVerified({
      publish: () => hostArtifact(value, {
        root: DEFAULT_PUBLISH_ROOT,
        scope: exposeToTailscale ? "tailscale" : "local",
        liveReload,
      }),
      verify: (artifact) => verifiedUrls(artifact.id, artifact.relativePath, exposeToTailscale),
      remove: (id) => removeArtifact(id, { root: DEFAULT_PUBLISH_ROOT }),
    });
    process.stdout.write(`${JSON.stringify({
      ...published.artifact,
      ...published.verification,
    })}\n`);
    return;
  }
  if (command === "remove" && value) {
    if (flags.length > 0) throw new Error("unknown remove option");
    await removeArtifact(value, { root: DEFAULT_PUBLISH_ROOT });
    process.stdout.write(`${JSON.stringify({ removed: value })}\n`);
    return;
  }
  if (command === "update" && value) {
    const [input, ...options] = flags;
    if (!input || options.length > 0) throw new Error("usage: host-artifact update ARTIFACT_ID PATH");
    await ensureReady({ isHealthy, ensureService });
    const artifact = await updateArtifact(value, input, { root: DEFAULT_PUBLISH_ROOT });
    const verification = await verifiedUrls(
      artifact.id,
      artifact.relativePath,
      artifact.id.startsWith("tailscale-"),
    );
    process.stdout.write(`${JSON.stringify({ ...artifact, ...verification })}\n`);
    return;
  }
  if (command === "status") {
    const healthy = await isHealthy();
    const tailscale = healthy ? await readyTailscaleAddress() : undefined;
    process.stdout.write(`${JSON.stringify({
      healthy,
      localhost: base,
      ...(tailscale ? { tailscale: `http://${tailscale}:${DEFAULT_PORT}` } : {}),
    })}\n`);
    if (!healthy) process.exitCode = 1;
    return;
  }
  throw new Error("usage: host-artifact <host PATH [--tailscale] [--no-reload] | update ARTIFACT_ID PATH | remove ARTIFACT_ID | status>");
}

main().catch((error: unknown) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
