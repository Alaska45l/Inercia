<script lang="ts">
  import { onMount } from 'svelte';
  import ConnectsTracker from './lib/components/ConnectsTracker.svelte';
  import FilterChips from './lib/components/FilterChips.svelte';
  import ProposalCard from './lib/components/ProposalCard.svelte';
  import StatsPanel from './lib/components/StatsPanel.svelte';
  import {
    connectProposalsSocket,
    connectionState,
    connects,
    filteredProposals,
    lastError,
    stats
  } from './lib/stores/proposals';

  onMount(() => {
    connectProposalsSocket();
  });
</script>

<main class="app-shell">
  <div class="glyph-rail" aria-hidden="true">
    <span></span>
    <span></span>
    <span></span>
  </div>
  <aside class="sidebar">
    <div class="brand-block">
      <div class="mark">
        <span>I</span>
      </div>
      <div>
        <h1>Inercia</h1>
        <p class:online={$connectionState === 'connected'}>{$connectionState}</p>
      </div>
    </div>

    <div class="status-board" aria-hidden="true">
      <span class:lit={$connectionState === 'connected'}></span>
      <span></span>
      <span class="warm"></span>
      <span></span>
      <span></span>
      <span class:lit={$filteredProposals.length > 0}></span>
    </div>

    <ConnectsTracker balance={$connects} />
    <StatsPanel stats={$stats} />
  </aside>

  <section class="workspace">
    <header class="topbar">
      <div>
        <p class="eyebrow">Proposal queue</p>
        <h2>Human approval</h2>
      </div>
      <FilterChips />
    </header>

    {#if $lastError}
      <div class="error-line">{$lastError}</div>
    {/if}

    <div class="proposal-grid">
      {#if $filteredProposals.length === 0}
        <div class="empty-state">
          <h3>No proposals</h3>
          <p>Waiting for the pipeline.</p>
        </div>
      {:else}
        {#each $filteredProposals as proposal (proposal.proposal_id)}
          <ProposalCard {proposal} />
        {/each}
      {/if}
    </div>
  </section>
</main>
