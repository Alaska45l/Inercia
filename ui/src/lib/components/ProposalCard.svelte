<script lang="ts">
  import ApprovalBar from './ApprovalBar.svelte';
  import type { Proposal } from '../stores/proposals';

  export let proposal: Proposal;

  let expanded = false;

  $: country = proposal.client_country || 'Unknown';
  $: rateLabel = proposal.bid_type === 'hourly' ? `$${proposal.bid_rate.toFixed(0)}/hr` : `$${proposal.bid_rate.toFixed(0)}`;
  $: statusLocked = proposal.status === 'rejected' || proposal.status === 'submitted';
</script>

<article
  class="proposal-card"
  class:pending={proposal.status === 'pending'}
  class:approved={proposal.status === 'approved'}
  class:rejected={proposal.status === 'rejected'}
  class:submitted={proposal.status === 'submitted'}
>
  <header class="proposal-head">
    <div>
      <h3>{proposal.title}</h3>
      <p>{country}</p>
    </div>
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
    <p class:clamped={!expanded}>{proposal.cover_letter}</p>
    <button type="button" on:click={() => (expanded = !expanded)}>
      {expanded ? 'show less' : 'show more'}
    </button>
  </section>

  {#if expanded && Object.keys(proposal.screening_answers).length > 0}
    <dl class="answer-list">
      {#each Object.entries(proposal.screening_answers) as [question, answer]}
        <div>
          <dt>{question}</dt>
          <dd>{answer}</dd>
        </div>
      {/each}
    </dl>
  {/if}

  <ApprovalBar
    proposalId={proposal.proposal_id}
    coverLetter={proposal.cover_letter}
    status={proposal.status}
    disabled={statusLocked}
  />
</article>
