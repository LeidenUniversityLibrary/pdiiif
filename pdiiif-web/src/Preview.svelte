<script lang="ts">
  import { _ } from 'svelte-i18n';

  import type { ManifestInfo } from './iiif';
  import Spinner from './Spinner.svelte';
  import type { Estimation } from 'pdiiif';

  export let infoPromise: Promise<ManifestInfo | void>;
  export let estimatePromise: Promise<Estimation> | undefined;
  export let canvasIdentifiers: string[] | undefined;
</script>

<div class="flex flex-col sm:flex-row items-start bg-indigo-50 p-4 rounded-md mb-4 overflow-hidden">
  {#await infoPromise}
    <Spinner />
  {:then manifestInfo}
    {#if manifestInfo}
      <img
        src={manifestInfo.previewImageUrl}
        alt="preview"
        class="w-32 max-h-52 mb-4 sm:mb-0 sm:mr-8 object-contain flex-none"
      />
      <div class="min-w-0 flex-1">
        <h2 class="manifest-title font-bold text-lg" title={manifestInfo.label}>
          {manifestInfo.label}
        </h2>
        <ul class="mt-4">
          <li>
            {canvasIdentifiers?.length || manifestInfo.canvasIds.length}
            {$_('number_of_pages')}
          </li>
          {#if estimatePromise}
            <li>
              {#await estimatePromise}
                {$_('estimated_pdf_size')}:
                <Spinner />
              {:then { size, optimizationResult }}
                {#if size > 0}
                  {$_('estimated_pdf_size')}:
                  <strong>{(size / 1024 / 1024).toFixed(2)} MiB</strong>
                  {#if optimizationResult !== undefined}
                    <span class="block"
                      >{$_('optimized_size', {
                        values: {
                          sizePercent: (optimizationResult * 100).toFixed(0),
                        },
                      })}</span
                    >
                  {/if}
                {:else}
                  <strong class="text-red-400">{$_('errors.estimate_failure')}</strong>
                {/if}
              {:catch}
                <strong class="text-red-400">{$_('errors.estimate_failure')}</strong>
              {/await}
            </li>
          {/if}
        </ul>
      </div>
    {:else}
      <p class="text-red-400">{$_('errors.estimate_failure')}</p>
    {/if}
  {:catch}
    <p class="text-red-400">{$_('errors.estimate_failure')}</p>
  {/await}
</div>

<style>
  .manifest-title {
    display: -webkit-box;
    overflow: hidden;
    overflow-wrap: anywhere;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 5;
  }
</style>
