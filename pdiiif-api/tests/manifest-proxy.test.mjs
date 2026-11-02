import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  fetchPublicManifest,
  InvalidManifestUrlError,
  validateManifestUrl,
} from '../dist/manifest-proxy.js';

test('allows a public HTTPS manifest URL', async () => {
  const url = await validateManifestUrl('https://1.1.1.1/manifest');
  assert.equal(url.protocol, 'https:');
});

test('rejects private addresses and credentials', async () => {
  for (const url of [
    'http://127.0.0.1/manifest',
    'http://10.0.0.1/manifest',
    'http://[::1]/manifest',
    'http://[::ffff:127.0.0.1]/manifest',
    'https://user:password@1.1.1.1/manifest',
    'file:///etc/passwd',
  ]) {
    await assert.rejects(validateManifestUrl(url), InvalidManifestUrlError);
  }
});

test('rejects a redirect to a private address before fetching it', async () => {
  const originalFetch = globalThis.fetch;
  let requestCount = 0;
  globalThis.fetch = async () => {
    requestCount += 1;
    return new Response(null, {
      status: 302,
      headers: { Location: 'http://127.0.0.1/private' },
    });
  };
  try {
    await assert.rejects(
      fetchPublicManifest('https://1.1.1.1/manifest'),
      InvalidManifestUrlError
    );
    assert.equal(requestCount, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
