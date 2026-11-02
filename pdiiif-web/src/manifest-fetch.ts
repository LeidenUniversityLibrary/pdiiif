/** Fetch manifests directly with a simple Accept header, using the API if CORS blocks access. */
export function createManifestFetch(apiEndpoint: string): typeof fetch {
  return async (input, init) => {
    const manifestUrl =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const headers = new Headers(input instanceof Request ? input.headers : init?.headers);
    if (new URL(manifestUrl, window.location.href).origin !== window.location.origin) {
      headers.set('Accept', '*/*');
    }

    try {
      const response = await fetch(input, { ...init, headers });
      if (!response.ok) {
        throw new Error(`Manifest returned HTTP ${response.status}`);
      }
      return response;
    } catch (err) {
      if (!(err instanceof TypeError)) {
        throw err;
      }
    }

    const proxyUrl = new URL(`${apiEndpoint}/proxy-manifest`, window.location.href);
    proxyUrl.searchParams.set('manifestUrl', manifestUrl);
    const response = await fetch(proxyUrl, init);
    if (!response.ok) {
      throw new Error(`Manifest proxy returned HTTP ${response.status}`);
    }
    return response;
  };
}
