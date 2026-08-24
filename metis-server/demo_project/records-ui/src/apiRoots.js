// Frozen literal values, so `apiRoots.record` is constant resolution rather than
// a guess. A computed root is reported unresolved instead of being invented.
export const apiRoots = Object.freeze({
  record: "/record",
  summary: "/summary",
});

export async function requestJson(root, path) {
  const response = await fetch(root + path);
  return response.json();
}
