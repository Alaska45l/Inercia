<script lang="ts">
  import { approveProposal, confirmSubmitted, rejectProposal, saveEditedLetter } from '../stores/proposals';
  import type { ProposalStatus } from '../stores/proposals';

  export let proposalId: number;
  export let coverLetter: string;
  export let status: ProposalStatus = 'pending';
  export let disabled = false;

  let editing = false;
  let draft = coverLetter;

  $: canApprove = status === 'pending' && !disabled;
  $: canReject = (status === 'pending' || status === 'approved') && !disabled;
  $: canEdit = status === 'pending' && !disabled;
  $: canConfirmSubmitted = status === 'approved' && !disabled;

  $: if (!editing) {
    draft = coverLetter;
  }

  function save(): void {
    saveEditedLetter(proposalId, draft);
    editing = false;
  }
</script>

<div class="approval-bar">
  {#if status === 'pending'}
    <button class="accept" type="button" disabled={!canApprove} title="Accept proposal" on:click={() => approveProposal(proposalId)}>
      Accept
    </button>
  {/if}
  {#if status === 'pending' || status === 'approved'}
    <button class="reject" type="button" disabled={!canReject} title="Reject proposal" on:click={() => rejectProposal(proposalId)}>
      Reject
    </button>
  {/if}
  {#if status === 'pending'}
    <button class="edit" type="button" disabled={!canEdit} title="Edit cover letter" on:click={() => (editing = !editing)}>
      Edit
    </button>
  {/if}
  {#if status === 'approved'}
    <button
      class="accept"
      type="button"
      disabled={!canConfirmSubmitted}
      title="Confirm submitted"
      on:click={() => confirmSubmitted(proposalId)}
    >
      Submitted
    </button>
  {/if}
</div>

{#if editing && canEdit}
  <div class="editor-block">
    <textarea bind:value={draft} rows="7" aria-label="Cover letter editor"></textarea>
    <div class="editor-actions">
      <button type="button" on:click={save}>Save</button>
      <button type="button" on:click={() => (editing = false)}>Cancel</button>
    </div>
  </div>
{/if}
