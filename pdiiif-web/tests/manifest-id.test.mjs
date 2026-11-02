import assert from 'node:assert/strict';
import { test } from 'node:test';
import { vault } from 'pdiiif';
import { getManifestId } from '../src/manifest-id.ts';

test('loads a redirected manifest under the ID used by size estimation', async () => {
  const alias = 'https://iiif.example.org/manifest';
  const canonical = 'https://catalogue.example.org/manifest';
  const manifest = {
    '@context': 'http://iiif.io/api/presentation/3/context.json',
    id: canonical,
    type: 'Manifest',
    label: { en: ['Test manifest'] },
    items: [
      {
        id: `${canonical}/canvas/1`,
        type: 'Canvas',
        width: 100,
        height: 100,
        items: [
          {
            id: `${canonical}/page/1`,
            type: 'AnnotationPage',
            items: [
              {
                id: `${canonical}/annotation/1`,
                type: 'Annotation',
                motivation: 'painting',
                target: `${canonical}/canvas/1`,
                body: {
                  id: 'https://images.example.org/image.jpg',
                  type: 'Image',
                  format: 'image/jpeg',
                  width: 100,
                  height: 100,
                },
              },
            ],
          },
        ],
      },
    ],
  };

  const loaded = await vault.loadManifest(getManifestId(alias, manifest), manifest);
  assert.equal(loaded.id, canonical);

  const reloaded = await Promise.race([
    vault.loadManifest(canonical, manifest),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Canonical vault load stayed pending')), 1000)
    ),
  ]);
  assert.equal(reloaded.id, canonical);
});

test('uses the IIIF 2 identifier or request URL when no v3 ID exists', () => {
  assert.equal(
    getManifestId('https://example.org/alias', { '@id': 'https://example.org/v2' }),
    'https://example.org/v2'
  );
  assert.equal(getManifestId('https://example.org/alias', {}), 'https://example.org/alias');
});
