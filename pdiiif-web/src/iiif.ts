import type {
  ContentResource,
  IIIFExternalWebResource,
} from '@iiif/presentation-3';
import type {
  ManifestNormalized,
  CanvasNormalized,
  AnnotationPageNormalized,
  AnnotationNormalized,
} from '@iiif/presentation-3-normalized'
import { Vault,  createThumbnailHelper, getValue } from '@iiif/helpers';
import {
  supportsCustomSizes,
  getImageServices,
} from '@atlas-viewer/iiif-image-api';
import { fetchManifestJson } from 'pdiiif';
import { vault } from 'pdiiif';

const thumbHelper = createThumbnailHelper(vault);

export interface ManifestInfo {
  label: string;
  previewImageUrl?: string;
  manifest: ManifestNormalized;
  maximumImageWidth: number;
  supportsDownscale: boolean;
  canvasIds: string[];
}

export async function fetchManifestInfo(
  manifestUrl: string,
  apiEndpoint?: string
): Promise<ManifestInfo> {
  let manifestJson;
  
  // Try direct fetch first, fall back to proxy only if CORS fails
  try {
    manifestJson = await fetchManifestJson(manifestUrl);
  } catch (err) {
    // If direct fetch fails and we have a proxy endpoint, try using it
    if (apiEndpoint && (err as Error).message?.includes('CORS')) {
      console.log(`CORS error detected, falling back to proxy for: ${manifestUrl}`);
      const encodedUrl = encodeURIComponent(manifestUrl);
      const proxyUrl = `${apiEndpoint}/proxy-manifest?manifestUrl=${encodedUrl}`;
      const response = await window.fetch(proxyUrl);
      if (!response.ok) {
        throw new Error(`Failed to fetch manifest via proxy: ${response.statusText}`);
      }
      manifestJson = await response.json();
    } else {
      // Re-throw if it's not a CORS issue or we don't have a proxy
      throw err;
    }
  }
  
  const manifest = (await vault.loadManifest(manifestUrl, manifestJson))!;
  const canvases = vault.get<CanvasNormalized>(manifest.items);
  const canvasIds = canvases.map((c) => c.id);
  const images = canvases
    .flatMap((c) => vault.get<AnnotationPageNormalized>(c.items))
    .flatMap((ap) => vault.get<AnnotationNormalized>(ap.items))
    .flatMap((a) => vault.get<ContentResource>(a.body.map(b => b.id)))
    .flatMap((r) => {
      if ((r as any).type === 'Choice') {
        return vault.get<ContentResource>(
          (r as any).items.filter((i: any) => i.type === 'ContentResource')
        );
      } else {
        return [r];
      }
    })
    .filter(
      (r: ContentResource): r is IIIFExternalWebResource => r.type === 'Image'
    );
  const thumbInfo = await thumbHelper.getBestThumbnailAtSize(manifest, {
    maxWidth: 300,
    maxHeight: 300,
  });

  const previewImageUrl = thumbInfo.best?.id ?? images[0].id;

  const supportsDownscale =
    images.flatMap(getImageServices).find(supportsCustomSizes) !== undefined;

  const maximumImageWidth = Math.max(...images.map((i) => i.width ?? 0));

  return {
    label: getValue(manifest.label),
    previewImageUrl,
    maximumImageWidth,
    manifest,
    supportsDownscale,
    canvasIds,
  };
}
