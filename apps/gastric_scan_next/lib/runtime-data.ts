import os from 'os';
import path from 'path';

const configuredRuntimeDir = process.env.GASTRIC_RUNTIME_DATA_DIR?.trim();

/**
 * Runtime outputs must stay outside the Next.js source tree.
 *
 * Next dev watches files below the app directory. Persisting audit events or
 * manual overrides in `app/data` therefore triggers Fast Refresh after every
 * user action and can interrupt client-side navigation.
 */
const defaultRuntimeDir = process.env.NODE_ENV === 'development'
  ? path.join(os.tmpdir(), 'gastric-scan-next')
  : path.resolve(process.cwd(), '..', 'runtime-data');
const runtimeDir = configuredRuntimeDir
  ? path.resolve(configuredRuntimeDir)
  : defaultRuntimeDir;

export function runtimeDataFile(filename: string): string {
  return path.join(runtimeDir, filename);
}

export function legacyAppDataFile(filename: string): string {
  return path.join(process.cwd(), 'data', filename);
}
