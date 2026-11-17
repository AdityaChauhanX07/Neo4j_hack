import { copyFile, mkdir } from "node:fs/promises";

const output = new URL("./dist/licenses/", import.meta.url);
const licenses = {
  "Apache-2.0.txt": "../LICENSE",
  "Cytoscape.txt": "./node_modules/cytoscape/LICENSE",
  "Geist.txt": "./node_modules/@fontsource-variable/geist/LICENSE",
};

await mkdir(output, { recursive: true });
await Promise.all(Object.entries(licenses).map(([name, file]) => (
  copyFile(new URL(file, import.meta.url), new URL(name, output))
)));
