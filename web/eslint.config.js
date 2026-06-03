import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "public", "node_modules", "playwright-report", "test-results"] },
  ...tseslint.configs.recommended,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
