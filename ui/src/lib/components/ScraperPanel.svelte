<script lang="ts">
  import { lastScrapeResult, runScrape, scrapeRunning } from '../stores/proposals';

  let query = '';
  let allowNetwork = false;

  function submitScrape(): void {
    runScrape(query, allowNetwork);
  }
</script>

<section class="control-panel">
  <div class="scraper-row">
    <input class="control-input" type="text" bind:value={query} placeholder="upwork query" />
    <label class="toggle-row">
      <span>Live network</span>
      <input type="checkbox" bind:checked={allowNetwork} />
      <span class="toggle-visual" aria-hidden="true"></span>
    </label>
    <button class="control-button" type="button" disabled={$scrapeRunning} on:click={submitScrape}>Run</button>
  </div>

  <div class="status-line">
    {#if $scrapeRunning}
      <span class="running-pulse">running</span>
    {:else if $lastScrapeResult}
      {$lastScrapeResult}
    {:else}
      idle
    {/if}
  </div>
</section>
