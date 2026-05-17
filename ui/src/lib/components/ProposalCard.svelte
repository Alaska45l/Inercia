<script lang="ts">
  import ApprovalBar from './ApprovalBar.svelte';
  import type { Proposal } from '../stores/proposals';

  export let proposal: Proposal;

  let expanded = false;

  $: country = proposal.client_country || 'Unknown';
  $: rateLabel = proposal.bid_type === 'hourly' ? `$${proposal.bid_rate.toFixed(0)}/hr` : `$${proposal.bid_rate.toFixed(0)}`;
  $: preview = proposal.cover_letter.split(/\s+/).slice(0, 34).join(' ');
  $: statusLocked = proposal.status !== 'pending';
</script>

<article class="proposal-card">
  <div class="card-hardware" aria-hidden="true">
    <span></span>
    <span></span>
  </div>
  <header class="proposal-head">
    <div>
      <h3>{proposal.title}</h3>
      <p>{country}</p>
    </div>
    <span class={`status-badge ${proposal.status}`}>{proposal.status}</span>
  </header>

  <div class="metric-row">
    <div class="metric roi">
      <span>ROI</span>
      <strong>{proposal.roi_score.toFixed(1)}</strong>
    </div>
    <div class="metric">
      <span>Connects</span>
      <strong>{proposal.connects_cost}</strong>
    </div>
    <div class="metric">
      <span>Bid</span>
      <strong>{rateLabel}</strong>
    </div>
  </div>

  <section class="letter-preview">
    <div class="letter-label">
      <span>Cover</span>
      <i aria-hidden="true"></i>
    </div>
    <div class:clamped={!expanded}>
      {#if expanded}
        {proposal.cover_letter}
      {:else}
        {preview}
      {/if}
    </div>
    <button type="button" on:click={() => (expanded = !expanded)}>
      {expanded ? 'Close' : 'Open'}
    </button>
  </section>

  {#if expanded && Object.keys(proposal.screening_answers).length > 0}
    <section class="answers-block">
      {#each Object.entries(proposal.screening_answers) as [question, answer]}
        <div>
          <h4>{question}</h4>
          <p>{answer}</p>
        </div>
      {/each}
    </section>
  {/if}

  <ApprovalBar proposalId={proposal.proposal_id} coverLetter={proposal.cover_letter} disabled={statusLocked} />
</article>
