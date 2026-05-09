import { createHash } from "node:crypto";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const publicDir = join(root, "public");
const indexPath = join(publicDir, "index.html");
let html = readFileSync(indexPath, "utf8");

function hexDigest(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex").slice(0, 10);
}

function rewriteOutlierAsset(ext) {
  const pattern = new RegExp(`/assets/outlier-[A-Za-z0-9_-]+\\.${ext}`, "g");
  const matches = [...new Set(html.match(pattern) || [])];
  for (const match of matches) {
    const oldRel = match.slice(1);
    const oldPath = join(publicDir, oldRel);
    if (!existsSync(oldPath)) continue;
    const digest = hexDigest(oldPath);
    const newRel = `assets/outlier-${digest}.${ext}`;
    const newPath = join(publicDir, newRel);
    if (oldPath !== newPath) {
      renameSync(oldPath, newPath);
    }
    if (ext === "js") {
      const oldMap = `${oldPath}.map`;
      const newMap = `${newPath}.map`;
      if (existsSync(oldMap)) {
        renameSync(oldMap, newMap);
        let js = readFileSync(newPath, "utf8");
        js = js.replace(/sourceMappingURL=outlier-[^\n]+\.js\.map/, `sourceMappingURL=outlier-${digest}.js.map`);
        writeFileSync(newPath, js);
      }
    }
    html = html.split(match).join(`/${newRel}`);
  }
}

rewriteOutlierAsset("js");
rewriteOutlierAsset("css");
writeFileSync(indexPath, html);

const manifestPath = join(publicDir, ".vite", "manifest.json");
if (existsSync(manifestPath)) {
  let manifest = readFileSync(manifestPath, "utf8");
  const jsMatch = html.match(/\/assets\/(outlier-[a-f0-9]{10}\.js)/);
  const cssMatch = html.match(/\/assets\/(outlier-[a-f0-9]{10}\.css)/);
  if (jsMatch) manifest = manifest.replace(/assets\/outlier-[A-Za-z0-9_-]+\.js/g, `assets/${jsMatch[1]}`);
  if (cssMatch) manifest = manifest.replace(/assets\/outlier-[A-Za-z0-9_-]+\.css/g, `assets/${cssMatch[1]}`);
  writeFileSync(manifestPath, manifest);
}
