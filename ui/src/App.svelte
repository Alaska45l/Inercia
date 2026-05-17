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
  <aside class="sidebar">
    <div class="brand-block">
      <h1>INERCIA</h1>
      <span
        class="connection-dot"
        class:connected={$connectionState === 'connected'}
        aria-label={`Connection ${$connectionState}`}
        title={$connectionState}
      ></span>
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
          <p>No proposals.</p>
        </div>
      {:else}
        {#each $filteredProposals as proposal (proposal.proposal_id)}
          <ProposalCard {proposal} />
        {/each}
      {/if}
    </div>
  </section>
</main>
