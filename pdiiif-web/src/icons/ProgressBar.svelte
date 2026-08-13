<script lang="ts">
  export let currentProgress: { current: number; total: number };

  $: progressPercent = (currentProgress.current / currentProgress.total) * 100;
  $: progressBarStyle = `width: ${progressPercent}%; background: var(--accent);`;
</script>

<div
  class="relative mt-4 h-8 w-full rounded-lg overflow-hidden"
  style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.1);"
>
  <div class="h-full rounded-lg transition-all" style={progressBarStyle} />
  <div
    class="absolute w-full top-0 pt-1 text-center text-white font-semibold"
  >
    <slot />
  </div>
</div>
