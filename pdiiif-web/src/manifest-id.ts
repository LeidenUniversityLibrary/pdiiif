/** Use the identifier in the manifest so subsequent vault loads use the same key. */
export function getManifestId(
  requestUrl: string,
  manifest: { id?: unknown; '@id'?: unknown }
): string {
  if (typeof manifest.id === 'string' && manifest.id) {
    return manifest.id;
  }
  if (typeof manifest['@id'] === 'string' && manifest['@id']) {
    return manifest['@id'];
  }
  return requestUrl;
}
