import { writeFileSync } from "node:fs";
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const docsDir = path.join(root, "docs");

export default defineConfig({
  root: path.join(root, "web"),
  base: "./",
  build: {
    outDir: docsDir,
    emptyOutDir: true,
  },
  plugins: [
    {
      name: "nojekyll",
      closeBundle() {
        writeFileSync(path.join(docsDir, ".nojekyll"), "");
      },
    },
  ],
});
