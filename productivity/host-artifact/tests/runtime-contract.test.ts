import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const skillRoot = path.resolve(import.meta.dirname, "..");

async function exists(relativePath: string): Promise<boolean> {
  try {
    await access(path.join(skillRoot, relativePath));
    return true;
  } catch {
    return false;
  }
}

test("Bun runs TypeScript sources without committed JavaScript bundles", async () => {
  // Arrange: Runtime metadata is the deployment contract used by LaunchAgent and agents.
  const packageJson = JSON.parse(
    await readFile(path.join(skillRoot, "package.json"), "utf8"),
  ) as {
    scripts: Record<string, string>;
    dependencies: Record<string, string>;
    devDependencies: Record<string, string>;
  };

  // Act: Inspect runtime entrypoints and generated-artifact presence.
  const buildScriptExists = await exists("build.mjs");
  const distExists = await exists("dist");

  // Assert: Production executes checked-in TypeScript and does not retain a second JS implementation.
  assert.equal(packageJson.scripts.server, "bun run src/server-main.ts");
  assert.equal(packageJson.scripts["host-artifact"], "bun run src/cli.ts");
  assert.equal(packageJson.dependencies["@hono/node-server"], undefined);
  assert.equal(packageJson.devDependencies.esbuild, undefined);
  assert.equal(packageJson.devDependencies.tsx, undefined);
  assert.equal(buildScriptExists, false);
  assert.equal(distExists, false);
});
