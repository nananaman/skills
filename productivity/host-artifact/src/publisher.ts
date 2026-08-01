import { randomBytes } from "node:crypto";
import { execFile } from "node:child_process";
import { cp, lstat, mkdir, readFile, realpath, readdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { ARTIFACT_NAME_PATTERN, REVISION_PATTERN, WORKSPACE_PATTERN, artifactRoute } from "./config.js";
import { withLiveReload } from "./live-reload.js";

export type ArtifactKind = "html" | "svg" | "pdf" | "png" | "jpeg" | "gif" | "webp" | "avif" | "directory";
export interface ArtifactMetadata { schemaVersion: 1; workspace: string; name: string; revision: string; kind: ArtifactKind; entry: string; updatedAt: string }
export interface PublishedArtifact extends ArtifactMetadata { route: string }
export interface RecoveryOperations {
  removeStaging(path: string): Promise<void>;
  removeTemporaryCurrent(path: string): Promise<void>;
  restoreCurrent(currentPath: string, previous: string | undefined, artifactRoot: string, revision: string): Promise<void>;
  removeDestination(path: string): Promise<void>;
}
export interface CommitOperations {
  writeTemporaryCurrent(path: string, metadata: string): Promise<void>;
  switchCurrent(temporary: string, current: string): Promise<void>;
}
export interface PublisherOptions { root: string; workspace: string; name: string; revisionGenerator?: () => string; now?: () => Date; lockAttempts?: number; verify?: (artifact: PublishedArtifact) => Promise<void>; recovery?: Partial<RecoveryOperations>; commit?: Partial<CommitOperations> }

const FILE_KINDS: Record<string, ArtifactKind> = {
  ".html": "html", ".htm": "html", ".svg": "svg", ".pdf": "pdf", ".png": "png",
  ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".webp": "webp", ".avif": "avif",
};

function validateKey(workspace: string, name: string): void {
  if (!WORKSPACE_PATTERN.test(workspace)) throw new Error("invalid workspace segment");
  if (!ARTIFACT_NAME_PATTERN.test(name)) throw new Error("invalid artifact name");
}

async function validateTree(input: string): Promise<void> {
  const stat = await lstat(input);
  if (stat.isSymbolicLink()) throw new Error("symlink input is not allowed");
  if (path.basename(input).startsWith(".")) throw new Error("dotfile input is not allowed");
  if (stat.isFile()) return;
  if (!stat.isDirectory()) throw new Error("special file input is not allowed");
  for (const entry of await readdir(input)) await validateTree(path.join(input, entry));
}

async function validatedRoot(root: string): Promise<string> {
  const resolved = path.resolve(root);
  const stat = await lstat(resolved);
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error("publish root must be a real directory");
  return realpath(resolved);
}

async function ensureManagedDirectory(root: string, segments: string[]): Promise<string> {
  let current = root;
  for (const segment of segments) {
    current = path.join(current, segment);
    try { await mkdir(current); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
    const stat = await lstat(current);
    if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error("managed directory must be a real directory");
    const resolved = await realpath(current);
    if (resolved !== current || !resolved.startsWith(`${root}${path.sep}`)) throw new Error("managed directory escapes publish root");
  }
  return current;
}

const execFileAsync = promisify(execFile);
async function acquireLock(lock: string, attempts = 50): Promise<() => Promise<void>> {
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      await execFileAsync("/usr/bin/shlock", ["-p", String(process.pid), "-f", lock]);
      return async () => {
        try {
          if ((await readFile(lock, "utf8")).trim() === String(process.pid)) await rm(lock);
        } catch { /* Never remove a lock whose ownership cannot be proven. */ }
      };
    } catch {
      if (attempt + 1 === attempts) throw new Error("artifact lock acquisition timed out");
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
  }
  throw new Error("artifact lock acquisition timed out");
}

async function classify(source: string): Promise<{ kind: ArtifactKind; entry: string; directory: boolean }> {
  const stat = await lstat(source);
  if (stat.isDirectory()) {
    const index = path.join(source, "index.html");
    try {
      const indexStat = await lstat(index);
      if (!indexStat.isFile() || indexStat.isSymbolicLink()) throw new Error();
    } catch { throw new Error("directory must contain a regular top-level index.html"); }
    return { kind: "directory", entry: "index.html", directory: true };
  }
  if (!stat.isFile()) throw new Error("input must be a regular file or directory");
  const kind = FILE_KINDS[path.extname(source).toLowerCase()];
  if (!kind) throw new Error("input is not a supported browser artifact");
  return { kind, entry: path.basename(source), directory: false };
}

export async function publishArtifact(input: string, options: PublisherOptions): Promise<PublishedArtifact> {
  validateKey(options.workspace, options.name);
  const source = path.resolve(input);
  await validateTree(source);
  const root = await validatedRoot(options.root);
  const classification = await classify(source);
  const revision = options.revisionGenerator?.() ?? `r-${randomBytes(16).toString("hex")}`;
  if (!REVISION_PATTERN.test(revision)) throw new Error("invalid generated revision");
  const artifactRoot = await ensureManagedDirectory(root, ["v2", "workspaces", options.workspace, "artifacts", options.name]);
  const release = await acquireLock(`${artifactRoot}.lock`, options.lockAttempts);
  try {
    await ensureManagedDirectory(root, ["v2", "workspaces", options.workspace, "artifacts", options.name, "revisions"]);
    const staging = path.join(artifactRoot, `staging-${revision}`);
    const destination = path.join(artifactRoot, "revisions", revision);
    const currentPath = path.join(artifactRoot, "current.json");
    let previousCurrent: string | undefined;
    try { previousCurrent = await readFile(currentPath, "utf8"); } catch {}
    let currentSwitched = false;
    let destinationCreated = false;
    const temporaryCurrent = path.join(artifactRoot, `.current-${revision}.json`);
    try {
      await mkdir(staging);
      if (classification.directory) await cp(source, staging, { recursive: true, dereference: false, errorOnExist: true });
      else await cp(source, path.join(staging, classification.entry), { errorOnExist: true });
      if (classification.kind === "html" || classification.kind === "directory") {
        const entry = path.join(staging, classification.entry);
        await writeFile(entry, withLiveReload(await readFile(entry), revision));
      }
      await validateTree(staging);
      if (await realpath(root) !== root) throw new Error("publish root identity changed");
      await rename(staging, destination);
      destinationCreated = true;
      const metadata: ArtifactMetadata = { schemaVersion: 1, workspace: options.workspace, name: options.name, revision, kind: classification.kind, entry: classification.entry, updatedAt: (options.now?.() ?? new Date()).toISOString() };
      await (options.commit?.writeTemporaryCurrent ?? ((target, body) => writeFile(target, body, { flag: "wx" })))(temporaryCurrent, `${JSON.stringify(metadata)}\n`);
      await (options.commit?.switchCurrent ?? rename)(temporaryCurrent, currentPath);
      currentSwitched = true;
      const published = { ...metadata, route: artifactRoute(options.workspace, options.name) };
      await options.verify?.(published);
      return published;
    } catch (error) {
      const recoveryErrors: Error[] = [];
      const record = async (operation: () => Promise<void>): Promise<boolean> => {
        try { await operation(); return true; }
        catch (recoveryError) { recoveryErrors.push(recoveryError instanceof Error ? recoveryError : new Error(String(recoveryError))); return false; }
      };
      await record(() => (options.recovery?.removeStaging ?? ((target) => rm(target, { recursive: true, force: true })))(staging));
      await record(() => (options.recovery?.removeTemporaryCurrent ?? ((target) => rm(target, { force: true })))(temporaryCurrent));
      if (currentSwitched) {
        const restored = await record(() => (options.recovery?.restoreCurrent ?? (async (target, previous, owner, id) => {
          if (previous !== undefined) { const rollback = path.join(owner, `.rollback-${id}.json`); await writeFile(rollback, previous, { flag: "wx" }); await rename(rollback, target); }
          else await rm(target, { force: true });
        }))(currentPath, previousCurrent, artifactRoot, revision));
        if (restored) await record(() => (options.recovery?.removeDestination ?? ((target) => rm(target, { recursive: true, force: true })))(destination));
      } else if (destinationCreated) await record(() => (options.recovery?.removeDestination ?? ((target) => rm(target, { recursive: true, force: true })))(destination));
      if (recoveryErrors.length > 0) {
        const primary = error instanceof Error ? error : new Error(String(error));
        throw new Error(`${primary.message}; recovery failures: ${recoveryErrors.map((item) => item.message).join("; ")}`, { cause: primary });
      }
      throw error;
    }
  } finally { await release(); }
}

export async function removeArtifact(options: Pick<PublisherOptions, "root" | "workspace" | "name" | "lockAttempts">): Promise<void> {
  validateKey(options.workspace, options.name);
  const root = await validatedRoot(options.root);
  const artifactsRoot = await ensureManagedDirectory(root, ["v2", "workspaces", options.workspace, "artifacts"]);
  const artifactRoot = path.join(artifactsRoot, options.name);
  try { const stat = await lstat(artifactRoot); if (stat.isSymbolicLink() || !stat.isDirectory() || await realpath(artifactRoot) !== artifactRoot) throw new Error("managed directory must be a real directory"); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") throw new Error("artifact does not exist"); throw error; }
  const release = await acquireLock(`${artifactRoot}.lock`, options.lockAttempts);
  try {
    if (await realpath(root) !== root) throw new Error("publish root identity changed");
    await rm(artifactRoot, { recursive: true, force: false });
  } finally { await release(); }
}

export function parseMetadata(value: unknown): ArtifactMetadata | undefined {
  if (typeof value !== "object" || value === null) return undefined;
  const v = value as Record<string, unknown>;
  if (v.schemaVersion !== 1 || typeof v.workspace !== "string" || !WORKSPACE_PATTERN.test(v.workspace) || typeof v.name !== "string" || !ARTIFACT_NAME_PATTERN.test(v.name) || typeof v.revision !== "string" || !REVISION_PATTERN.test(v.revision) || typeof v.kind !== "string" || !Object.values(FILE_KINDS).concat("directory").includes(v.kind as ArtifactKind) || typeof v.entry !== "string" || path.basename(v.entry) !== v.entry || typeof v.updatedAt !== "string" || Number.isNaN(Date.parse(v.updatedAt))) return undefined;
  return v as unknown as ArtifactMetadata;
}
