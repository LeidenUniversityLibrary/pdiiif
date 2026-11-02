/** Load the parser and encoder binaries from the application's API. */
export function createWasmLoader(apiEndpoint: string, filename: string) {
  return async (): Promise<Uint8Array> => {
    const response = await fetch(`${apiEndpoint}/wasm/${filename}`);
    if (!response.ok) {
      throw new Error(`Could not load ${filename}: HTTP ${response.status}`);
    }
    return new Uint8Array(await response.arrayBuffer());
  };
}
