// Inlines pdf.js and pdf-lib into one offline HTML file.
//   npm install            (in web/)
//   node build.mjs         -> ../dist/as-built-linker.html
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const lib = (p) => {
  const src = readFileSync(join(here, "node_modules", p), "utf8");
  if (/<\/script/i.test(src)) throw new Error(`${p} contains </script`);
  return src.replace(/\/\/# sourceMappingURL=.*$/gm, "");
};
let html = readFileSync(join(here, "as-built-linker.src.html"), "utf8");
const parts = {
  "/*PDFJS*/": lib("pdfjs-dist/legacy/build/pdf.min.js"),
  "/*PDFJS_WORKER*/": lib("pdfjs-dist/legacy/build/pdf.worker.min.js"),
  "/*PDFLIB*/": lib("pdf-lib/dist/pdf-lib.min.js"),
};
for (const [marker, code] of Object.entries(parts)) {
  if (!html.includes(marker)) throw new Error(`marker ${marker} missing`);
  html = html.replace(marker, () => code);
}
const out = join(here, "..", "dist", "as-built-linker.html");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, html);
console.log(`wrote ${out} (${(html.length / 1e6).toFixed(1)} MB)`);
