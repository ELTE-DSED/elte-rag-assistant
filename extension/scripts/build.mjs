import { build } from "esbuild";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const extensionRoot = resolve(scriptDir, "..");
const srcDir = resolve(extensionRoot, "src");
const distDir = resolve(extensionRoot, "dist");

const defaultApiBaseUrl =
  process.env.EXT_DEFAULT_API_BASE_URL?.trim() || "http://localhost:8001";

const sharedBuildConfig = {
  bundle: true,
  format: "iife",
  minify: false,
  platform: "browser",
  target: "chrome114",
  define: {
    __EXT_DEFAULT_API_BASE_URL__: JSON.stringify(defaultApiBaseUrl),
  },
};

async function bundleEntries() {
  await Promise.all([
    build({
      ...sharedBuildConfig,
      entryPoints: [resolve(srcDir, "content/index.tsx")],
      outfile: resolve(distDir, "content.js"),
    }),
    build({
      ...sharedBuildConfig,
      entryPoints: [resolve(srcDir, "background/index.ts")],
      outfile: resolve(distDir, "background.js"),
    }),
    build({
      ...sharedBuildConfig,
      entryPoints: [resolve(srcDir, "options/index.ts")],
      outfile: resolve(distDir, "options.js"),
    }),
  ]);
}

async function copyStaticFiles() {
  await cp(resolve(srcDir, "options/options.html"), resolve(distDir, "options.html"));
  await cp(resolve(srcDir, "options/options.css"), resolve(distDir, "options.css"));
}

async function writeManifest() {
  const manifestTemplate = JSON.parse(
    await readFile(resolve(srcDir, "manifest.template.json"), "utf8"),
  );

  manifestTemplate.version =
    process.env.npm_package_version || manifestTemplate.version || "0.1.0";

  await writeFile(
    resolve(distDir, "manifest.json"),
    `${JSON.stringify(manifestTemplate, null, 2)}\n`,
    "utf8",
  );
}

async function main() {
  await rm(distDir, { recursive: true, force: true });
  await mkdir(distDir, { recursive: true });

  await bundleEntries();
  await copyStaticFiles();
  await writeManifest();

  process.stdout.write(`Built extension into ${distDir}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exit(1);
});
