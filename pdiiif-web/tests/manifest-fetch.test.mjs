import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createManifestFetch } from '../src/manifest-fetch.ts';

const manifestUrl = 'https://catalogue.example.org/manifest?iiifVersion=3';
const apiEndpoint = 'https://pdf.example.org/api';

async function withBrowserFetch(fetchMock, run) {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: { href: 'https://pdf.example.org/', origin: 'https://pdf.example.org' },
  };
  globalThis.fetch = fetchMock;
  try {
    await run();
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }
}

test('uses a simple Accept header for a cross-origin manifest', async () => {
  const requests = [];
  await withBrowserFetch(async (url, init) => {
    requests.push({ url, init });
    return new Response('{}');
  }, async () => {
    const manifestFetch = createManifestFetch(apiEndpoint);
    await manifestFetch(manifestUrl, {
      headers: { Accept: 'application/ld+json;profile="http://iiif.io/api/presentation/3/context.json"' },
    });
  });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, manifestUrl);
  assert.equal(requests[0].init.headers.get('Accept'), '*/*');
});

test('falls back to the proxy after a direct network or CORS failure', async () => {
  const requests = [];
  await withBrowserFetch(async (url, init) => {
    requests.push({ url, init });
    if (requests.length === 1) {
      throw new TypeError('Failed to fetch');
    }
    return new Response('{}');
  }, async () => {
    const manifestFetch = createManifestFetch(apiEndpoint);
    await manifestFetch(manifestUrl, { headers: { Accept: 'application/ld+json' } });
  });
  assert.equal(requests.length, 2);
  assert.equal(requests[0].init.headers.get('Accept'), '*/*');
  assert.equal(requests[1].url.pathname, '/api/proxy-manifest');
  assert.equal(requests[1].url.searchParams.get('manifestUrl'), manifestUrl);
  assert.equal(requests[1].init.headers.Accept, 'application/ld+json');
});

test('does not proxy a manifest that returns HTTP 404', async () => {
  const requests = [];
  await withBrowserFetch(async (url) => {
    requests.push(url);
    return new Response(null, { status: 404 });
  }, async () => {
    const manifestFetch = createManifestFetch(apiEndpoint);
    await assert.rejects(manifestFetch(manifestUrl), /HTTP 404/);
  });
  assert.equal(requests.length, 1);
});
