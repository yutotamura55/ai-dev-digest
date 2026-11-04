import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // 書式は Prettier に任せ、ぶつかる規則を切る。
  prettier,
  // 検査しないファイル。eslint-config-next の既定の除外を上書きするため、既定の 4 つも書く。
  globalIgnores([
    // eslint-config-next の既定の除外。
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vitest のカバレッジの報告。
    "coverage/**",
  ]),
]);

export default eslintConfig;
