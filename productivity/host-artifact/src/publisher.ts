import { randomBytes } from "node:crypto";
import { cp, lstat, mkdir, readFile, realpath, readdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { ARTIFACT_ID_PATTERN } from "./config.js";
import type { Exposure } from "./config.js";
import { withLiveReload } from "./live-reload.js";

export interface PublisherOptions {
  root: string;
  idGenerator?: () => string;
  scope?: Exposure;
  liveReload?: boolean;
}

export interface HostedArtifact {
  id: string;
  relativePath: string;
}

async function validateTree(input: string): Promise<void> {
  const stat = await lstat(input);
  if (stat.isSymbolicLink()) throw new Error(`symlink input is not allowed: ${input}`);
  if (path.basename(input).startsWith(".")) throw new Error(`dotfile input is not allowed: ${input}`);
  if (stat.isFile()) return;
  if (!stat.isDirectory()) throw new Error(`special file input is not allowed: ${input}`);
  for (const entry of await readdir(input)) await validateTree(path.join(input, entry));
}

function validateId(id: string): void {
  if (!ARTIFACT_ID_PATTERN.test(id)) throw new Error("invalid artifact id");
}

async function validatePublishRoot(root: string): Promise<string> {
  const resolved = path.resolve(root);
  const rootStat = await lstat(resolved);
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) throw new Error("publish root must be a real directory");
  return realpath(resolved);
}

export async function hostArtifact(input: string, options: PublisherOptions): Promise<HostedArtifact> {
  const source = path.resolve(input);
  await validateTree(source);
  const root = await validatePublishRoot(options.root);
  const sourceStat = await lstat(source);
  const liveReload = sourceStat.isFile()
    && path.extname(source).toLowerCase() === ".html"
    && options.liveReload !== false;
  if (sourceStat.isDirectory()) {
    const index = path.join(source, "index.html");
    try {
      const indexStat = await lstat(index);
      if (!indexStat.isFile() || indexStat.isSymbolicLink()) throw new Error();
    } catch {
      throw new Error("directory must contain a regular top-level index.html");
    }
  }
  for (let attempt = 0; attempt < 16; attempt++) {
    const randomId = options.idGenerator?.() ?? randomBytes(16).toString("hex");
    if (!/^[a-f0-9]{32}$/.test(randomId)) throw new Error("invalid generated artifact id");
    const id = `${options.scope ?? "local"}${liveReload ? "-live" : ""}-${randomId}`;
    validateId(id);
    const temporary = path.join(root, `staging-${id}-${randomBytes(6).toString("hex")}`);
    const destination = path.join(root, id);
    try {
      await mkdir(temporary);
      const stat = sourceStat;
      let relativePath: string;
      if (stat.isDirectory()) {
        await cp(source, temporary, { recursive: true, dereference: false, errorOnExist: true });
        relativePath = "index.html";
      } else if (stat.isFile()) {
        relativePath = path.basename(source);
        const copied = path.join(temporary, relativePath);
        await cp(source, copied, { errorOnExist: true });
        if (liveReload) await writeFile(copied, withLiveReload(await readFile(copied)));
      } else {
        throw new Error("input must be a regular file or directory");
      }
      await validateTree(temporary);
      if (await realpath(root) !== root) throw new Error("publish root identity changed");
      await rename(temporary, destination);
      return { id, relativePath };
    } catch (error) {
      await rm(temporary, { recursive: true, force: true });
      if ((error as NodeJS.ErrnoException).code === "EEXIST" && !options.idGenerator) continue;
      throw error;
    }
  }
  throw new Error("could not allocate a unique artifact id");
}

export async function updateArtifact(
  id: string,
  input: string,
  options: Pick<PublisherOptions, "root">,
): Promise<HostedArtifact> {
  validateId(id);
  const source = path.resolve(input);
  await validateTree(source);
  const sourceStat = await lstat(source);
  if (!sourceStat.isFile()) throw new Error("update input must be a regular file");

  const root = await validatePublishRoot(options.root);
  const artifactRoot = path.join(root, id);
  const artifactStat = await lstat(artifactRoot);
  if (artifactStat.isSymbolicLink() || !artifactStat.isDirectory()) throw new Error("artifact must be a real directory");
  const entries = await readdir(artifactRoot);
  if (entries.length !== 1) throw new Error("only single-file artifacts can be updated");
  const relativePath = entries[0]!;
  if (relativePath !== path.basename(source)) throw new Error("update filename must match the hosted filename");

  const destination = path.join(artifactRoot, relativePath);
  const destinationStat = await lstat(destination);
  if (destinationStat.isSymbolicLink() || !destinationStat.isFile()) {
    throw new Error("only single-file artifacts can be updated");
  }
  const temporary = path.join(artifactRoot, `.update-${randomBytes(6).toString("hex")}`);
  try {
    await cp(source, temporary, { errorOnExist: true });
    const temporaryStat = await lstat(temporary);
    if (!temporaryStat.isFile() || temporaryStat.isSymbolicLink()) throw new Error("update copy must be a regular file");
    if (id.includes("-live-")) {
      await writeFile(temporary, withLiveReload(await readFile(temporary)));
    }
    if (await realpath(root) !== root || await realpath(artifactRoot) !== artifactRoot) {
      throw new Error("publish root identity changed");
    }
    await rename(temporary, destination);
    return { id, relativePath };
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
}

export async function removeArtifact(id: string, options: Pick<PublisherOptions, "root">): Promise<void> {
  validateId(id);
  const root = await validatePublishRoot(options.root);
  const target = path.join(root, id);
  if (await realpath(root) !== root) throw new Error("publish root identity changed");
  await rm(target, { recursive: true, force: false });
}
