import fs from "fs";
import path from "path";

type ResolvedDataPaths = {
  configuredPath: string;
  projectRoot: string;
  datasetDir: string;
};

const REPO_HINT_ENV_KEYS = [
  "DIRECTION_ANNOTATOR_DATA_ROOT",
  "GASTRIC_ROOT",
  "GASTRIC_TSTAGING_ROOT",
] as const;

function isRepoLikeRoot(dir: string): boolean {
  return fs.existsSync(path.join(dir, "dataset"));
}

function hasAnnotationBatch(dir: string): boolean {
  return (
    fs.existsSync(path.join(dir, "direction_annotation_batch.json")) ||
    fs.existsSync(path.join(dir, "data/annotation/batches/direction_annotation_batch.json"))
  );
}

function findNearestRepoLikeRoot(startDir: string): string | null {
  let current = path.resolve(startDir);

  while (true) {
    if (hasAnnotationBatch(current)) {
      return current;
    }

    if (isRepoLikeRoot(current)) {
      return current;
    }

    const parent = path.dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

function getDefaultConfiguredPath(): string {
  for (const envKey of REPO_HINT_ENV_KEYS) {
    const envPath = process.env[envKey];
    if (envPath && fs.existsSync(envPath)) {
      return path.resolve(envPath);
    }
  }

  const repoRoot = findNearestRepoLikeRoot(process.cwd());
  if (repoRoot) {
    return repoRoot;
  }

  const candidateDirs = [
    path.resolve(process.cwd(), "..", "dataset"),
    path.join(process.cwd(), "dataset"),
  ];

  const firstExistingDataset = candidateDirs.find((dir) => fs.existsSync(dir));
  return firstExistingDataset || process.cwd();
}

/**
 * Returns the user-selected path.
 * The selection can be either:
 * 1. the project root containing `direction_annotation_batch.json`, or
 * 2. the `dataset/` folder itself.
 */
export function getDataRoot(): string {
  return process.env.DATA_ROOT || process.env.DIRECTION_ANNOTATOR_DATA_ROOT || getDefaultConfiguredPath();
}

export function resolveConfiguredPaths(configuredPath = getDataRoot()): ResolvedDataPaths {
  const absolutePath = path.resolve(configuredPath);
  const looksLikeDatasetDir = path.basename(absolutePath) === "dataset";

  return {
    configuredPath: absolutePath,
    projectRoot: looksLikeDatasetDir ? path.dirname(absolutePath) : absolutePath,
    datasetDir: looksLikeDatasetDir ? absolutePath : path.join(absolutePath, "dataset"),
  };
}

export function getBatchFilePath(): string {
  const { projectRoot } = resolveConfiguredPaths();
  const canonical = path.join(projectRoot, "data/annotation/batches/direction_annotation_batch.json");
  if (fs.existsSync(canonical)) {
    return canonical;
  }
  return path.join(projectRoot, "direction_annotation_batch.json");
}

export function getSaveDir(): string {
  const { projectRoot } = resolveConfiguredPaths();
  const canonical = path.join(projectRoot, "data/annotation/outputs/direction_annotations");
  if (fs.existsSync(canonical)) {
    return canonical;
  }
  return path.join(projectRoot, "direction_annotations");
}

export function resolveDataPath(relPath: string): string | null {
  const { projectRoot, datasetDir } = resolveConfiguredPaths();
  const normalizedRelPath = relPath.replace(/\\/g, "/").replace(/^\/+/, "");

  const baseDir = normalizedRelPath === "dataset" || normalizedRelPath.startsWith("dataset/")
    ? datasetDir
    : projectRoot;
  const relativePart = normalizedRelPath === "dataset"
    ? ""
    : normalizedRelPath.startsWith("dataset/")
      ? normalizedRelPath.slice("dataset/".length)
      : normalizedRelPath;

  const abs = path.resolve(baseDir, relativePart);
  const allowedRoot = path.resolve(baseDir);
  if (abs !== allowedRoot && !abs.startsWith(`${allowedRoot}${path.sep}`)) return null;
  if (!fs.existsSync(abs)) return null;
  return abs;
}
