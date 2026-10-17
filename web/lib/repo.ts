// Links into the public repository (README, experiment reports).
export const REPO_URL = "https://github.com/ttadev24/FreshMesh";

/** A repo-relative path (e.g. "docs/experiments/fl-results.md") as a GitHub link on main. */
export function repoFileUrl(path: string): string {
  return `${REPO_URL}/blob/main/${path.replace(/^\/+/, "")}`;
}
