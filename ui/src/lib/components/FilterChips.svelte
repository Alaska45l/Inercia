<script lang="ts">
  import { filterMode, proposalCounts } from '../stores/proposals';

  type FilterChipMode = 'all' | 'pending' | 'approved' | 'rejected' | 'submitted';

  const filters: { label: string; value: FilterChipMode }[] = [
    { label: 'All', value: 'all' },
    { label: 'Pending', value: 'pending' },
    { label: 'Approved', value: 'approved' },
    { label: 'Rejected', value: 'rejected' },
    { label: 'Submitted', value: 'submitted' }
  ];
</script>

<div class="filter-chips" role="tablist" aria-label="Proposal filters">
  {#each filters as item}
    <button
      type="button"
      role="tab"
      class:active={$filterMode === item.value}
      aria-selected={$filterMode === item.value}
      on:click={() => filterMode.set(item.value)}
    >
      {item.label} ({$proposalCounts[item.value]})
    </button>
  {/each}
</div>
