import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    ".next-aliyun/**",
    ".next-public/**",
    ".next-test/**",
    ".next-ci/**",
    ".backups/**",
    "out/**",
    "build/**",
    "public/vendor/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
