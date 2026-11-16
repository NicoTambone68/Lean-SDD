import { resolve } from "node:path";

import tseslint from "typescript-eslint";

export default tseslint.config(tseslint.configs.strictTypeChecked, {
  languageOptions: {
    parserOptions: {
      project: "./tsconfig.json",
      tsconfigRootDir: resolve(import.meta.dirname, ".."),
    },
  },
  rules: {
    "@typescript-eslint/no-floating-promises": "error",
    "@typescript-eslint/no-misused-promises": "error",
  },
});
