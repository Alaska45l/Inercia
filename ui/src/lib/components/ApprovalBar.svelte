<script lang="ts">
  import { approveProposal, rejectProposal, saveEditedLetter } from '../stores/proposals';

  export let proposalId: number;
  export let coverLetter: string;
  export let disabled = false;

  let editing = false;
  let draft = coverLetter;

  $: if (!editing) {
    draft = coverLetter;
  }

  function save(): void {
    saveEditedLetter(proposalId, draft);
    editing = false;
  }
</script>

<div class="approval-bar">
  <button class="accept" type="button" disabled={disabled} title="Accept proposal" on:click={() => approveProposal(proposalId)}>
    <span></span>
    Accept
  </button>
  <button class="reject" type="button" disabled={disabled} title="Reject proposal" on:click={() => rejectProposal(proposalId)}>
    <span></span>
    Reject
  </button>
  <button class="edit" type="button" disabled={disabled} title="Edit cover letter" on:click={() => (editing = !editing)}>
    <span></span>
    Edit
  </button>
</div>

{#if editing}
  <div class="editor-block">
    <textarea bind:value={draft} rows="7" aria-label="Cover letter editor"></textarea>
    <div class="editor-actions">
      <button type="button" on:click={save}>Save</button>
      <button type="button" on:click={() => (editing = false)}>Cancel</button>
    </div>
  </div>
{/if}
