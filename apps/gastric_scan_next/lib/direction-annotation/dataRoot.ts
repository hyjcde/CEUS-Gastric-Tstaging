import fs from "fs";
import path from "path";
import { PROJECT_ROOT } from "@/lib/config";

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

function findNearestRepoLikeRoot(startDir: string): string | null {
  let current = path.resolve(startDir);

  while (true) {
    if (fs.existsSync(path.join(current, "direction_annotation_batch.json"))) {
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
  if (fs.existsSync(path.join(PROJECT_ROOT, "direction_annotation_batch.json")) || isRepoLikeRoot(PROJECT_ROOT)) {
    return PROJECT_ROOT;
  }

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
  const candidates = [
    path.join(projectRoot, "data", "annotation", "batches", "direction_annotation_batch.json"),
    path.join(projectRoot, "direction_annotation_batch.json"),
    path.join(projectRoot, "_compat", "direction_annotation_batch.json"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || candidates[0];
}

export function getSaveDir(): string {
  const { projectRoot } = resolveConfiguredPaths();
  const candidates = [
    path.join(projectRoot, "data", "annotation", "outputs", "direction_annotations"),
    path.join(projectRoot, "direction_annotations"),
    path.join(projectRoot, "_compat", "direction_annotations"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || candidates[0];
}

export function getDirectionAnnotationFilePath(imagePath: string): string {
  const safeName = imagePath
    .replace(/[/\\]/g, "__")
    .replace(/\.(jpg|jpeg|png|webp)$/i, "");
  return path.join(getSaveDir(), `${safeName}_direction.json`);
}

export function readDirectionAnnotationIfExists(imagePath: string) {
  const filePath = getDirectionAnnotationFilePath(imagePath);
  if (!fs.existsSync(filePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return null;
  }
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
