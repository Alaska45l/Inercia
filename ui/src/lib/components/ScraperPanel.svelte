<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    lastScrapeError,
    lastScrapeResult,
    runConfiguredScrape,
    schedulerStatus,
    scrapeRunning,
    startScheduler,
    stopScheduler
  } from '../stores/proposals';

  let displayedSeconds = 0;
  let countdownTimer: number | null = null;

  $: displayedSeconds = $schedulerStatus.running ? $schedulerStatus.next_run_in_seconds : 0;
  $: minutes = Math.floor(displayedSeconds / 60);
  $: seconds = String(displayedSeconds % 60).padStart(2, '0');

  onMount(() => {
    countdownTimer = window.setInterval(() => {
      if ($schedulerStatus.running && displayedSeconds > 0) {
        displayedSeconds -= 1;
      }
    }, 1000);
  });

  onDestroy(() => {
    if (countdownTimer !== null) {
      window.clearInterval(countdownTimer);
    }
  });

  function submitScrape(): void {
    runConfiguredScrape();
  }
</script>

<section class="control-panel">
  <div class="scraper-row">
    <button class="control-button" type="button" disabled={$scrapeRunning} on:click={submitScrape}>Run Scrape</button>
    {#if $schedulerStatus.running}
      <button class="control-button login-open" type="button" on:click={stopScheduler}>Stop Bot</button>
      <div class="status-line">next cycle {minutes}:{seconds}</div>
    {:else}
      <button class="control-button" type="button" on:click={startScheduler}>Start Bot</button>
      <div class="status-line">scheduler stopped</div>
    {/if}
  </div>

  <div class="status-line">
    {#if $scrapeRunning}
      <span class="running-pulse">running</span>
    {:else if $lastScrapeError}
      <span class="scrape-error">{$lastScrapeError}</span>
    {:else if $lastScrapeResult}
      {$lastScrapeResult}
    {:else}
      idle
    {/if}
  </div>
</section>
