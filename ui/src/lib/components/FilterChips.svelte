<script lang="ts">
  import { filterMode, proposalCounts } from '../stores/proposals';

  type FilterChipMode = 'all' | 'pending' | 'approved' | 'rejected';

  const filters: { label: string; value: FilterChipMode }[] = [
    { label: 'All', value: 'all' },
    { label: 'Pending', value: 'pending' },
    { label: 'Approved', value: 'approved' },
    { label: 'Rejected', value: 'rejected' }
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
      <span>{item.label}</span>
      <strong>{$proposalCounts[item.value]}</strong>
    </button>
  {/each}
</div>
