/**
 * Load and manage compiled DSC artifacts.
 */

import * as fs from "fs";
import * as path from "path";
import { CompiledArtifact } from "./evaluator";

export interface LoadedArtifact {
  artifact: CompiledArtifact;
  filePath: string;
  loadedAt: Date;
}

/**
 * Load all compiled artifacts from a directory.
 */
export function loadArtifacts(dir: string): LoadedArtifact[] {
  const artifacts: LoadedArtifact[] = [];

  if (!fs.existsSync(dir)) {
    return artifacts;
  }

  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".json"));

  for (const file of files) {
    const filePath = path.join(dir, file);
    try {
      const raw = fs.readFileSync(filePath, "utf-8");
      const artifact: CompiledArtifact = JSON.parse(raw);

      // Validate basic structure
      if (artifact.graph && artifact.graph.states && artifact.graph.transitions) {
        artifacts.push({
          artifact,
          filePath,
          loadedAt: new Date(),
        });
      }
    } catch {
      // Skip invalid files
    }
  }

  return artifacts;
}

/**
 * Watch a directory for artifact changes and reload.
 */
export function watchArtifacts(
  dir: string,
  onReload: (artifacts: LoadedArtifact[]) => void
): fs.FSWatcher | null {
  if (!fs.existsSync(dir)) {
    return null;
  }

  return fs.watch(dir, { persistent: false }, () => {
    const artifacts = loadArtifacts(dir);
    onReload(artifacts);
  });
}
