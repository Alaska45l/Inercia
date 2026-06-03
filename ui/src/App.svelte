<script lang="ts">
  import { onMount } from 'svelte';
  import ConnectsTracker from './lib/components/ConnectsTracker.svelte';
  import FilterChips from './lib/components/FilterChips.svelte';
  import JobsTable from './lib/components/JobsTable.svelte';
  import LoginPanel from './lib/components/LoginPanel.svelte';
  import ProposalCard from './lib/components/ProposalCard.svelte';
  import ScraperPanel from './lib/components/ScraperPanel.svelte';
  import SettingsPanel from './lib/components/SettingsPanel.svelte';
  import StatsPanel from './lib/components/StatsPanel.svelte';
  import {
    activePanel,
    connectProposalsSocket,
    connectionState,
    connects,
    filteredProposals,
    lastError,
    requestJobs,
    requestSettings,
    stats
  } from './lib/stores/proposals';
  import type { Panel } from './lib/stores/proposals';

  const tabs: Array<{ label: string; value: Panel }> = [
    { label: 'Proposals', value: 'proposals' },
    { label: 'Scraper', value: 'scraper' },
    { label: 'Jobs', value: 'jobs' },
    { label: 'Settings', value: 'settings' }
  ];

  onMount(() => {
    connectProposalsSocket();
  });

  function switchPanel(panel: Panel): void {
    activePanel.set(panel);
    if (panel === 'jobs') requestJobs();
    if (panel === 'settings') requestSettings();
  }

  function reloadApp(): void {
    window.location.reload();
  }
</script>

<svelte:boundary>
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
      <nav class="panel-tabs" aria-label="Workspace panels">
        {#each tabs as tab}
          <button
            type="button"
            class:active={$activePanel === tab.value}
            on:click={() => switchPanel(tab.value)}
          >
            {tab.label}
          </button>
        {/each}
      </nav>

      {#if $lastError}
        <div class="error-line">{$lastError}</div>
      {/if}

      {#if $activePanel === 'proposals'}
        <header class="topbar">
          <div>
            <p class="eyebrow">Proposal queue</p>
            <h2>Human approval</h2>
          </div>
          <FilterChips />
        </header>

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
      {:else if $activePanel === 'scraper'}
        <div class="panel-stack">
          <ScraperPanel />
          <LoginPanel />
        </div>
      {:else if $activePanel === 'jobs'}
        <JobsTable />
      {:else if $activePanel === 'settings'}
        <SettingsPanel />
      {/if}
    </section>
  </main>

  {#snippet failed(error)}
    <div class="error-boundary">
      <p>{error instanceof Error ? error.message : 'Inercia UI failed to render.'}</p>
      <button type="button" on:click={reloadApp}>Reload</button>
    </div>
  {/snippet}
</svelte:boundary>
