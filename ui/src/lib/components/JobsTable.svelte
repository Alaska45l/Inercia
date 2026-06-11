<script lang="ts">
  import { jobs, requestJobs } from '../stores/proposals';

  const filters: Array<{ label: string; value: string | null }> = [
    { label: 'all', value: null },
    { label: 'new', value: 'new' },
    { label: 'ready', value: 'ready' },
    { label: 'blacklisted', value: 'blacklisted' },
    { label: 'rejected', value: 'rejected' }
  ];

  let selectedStatus: string | null = null;

  function selectStatus(status: string | null): void {
    selectedStatus = status;
    requestJobs(status);
  }

  function statusClass(status: string): string {
    if (status === 'ready' || status === 'approved' || status === 'submitted') return 'is-ok';
    if (status === 'blacklisted' || status === 'rejected') return 'is-err';
    return 'is-muted';
  }

  function sourceLabel(source: string): string {
    return source.replace('upwork_', '');
  }
</script>

<section class="control-panel">
  <div class="job-filter-row">
    {#each filters as filter}
      <button
        type="button"
        class:active={selectedStatus === filter.value}
        on:click={() => selectStatus(filter.value)}
      >
        {filter.label}
      </button>
    {/each}
  </div>

  <div class="jobs-table-wrap">
    <table class="jobs-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Title</th>
          <th>Source</th>
          <th>Type</th>
          <th>Payment</th>
          <th class="numeric">Connects</th>
          <th class="numeric">ROI</th>
          <th>Status</th>
          <th>Scraped</th>
        </tr>
      </thead>
      <tbody>
        {#each $jobs as job (job.id)}
          <tr>
            <td>{job.id}</td>
            <td>
              {#if job.url}
                <a href={job.url} target="_blank" rel="noreferrer">{job.title}</a>
              {:else}
                {job.title}
              {/if}
              {#if job.posted_age_text}
                <div class="is-muted">{job.posted_age_text}</div>
              {/if}
            </td>
            <td>{sourceLabel(job.source)}</td>
            <td>{job.job_type}</td>
            <td class={job.client_payment_verified ? 'is-ok' : 'is-muted'}>{job.client_payment_verified ? 'verified' : '-'}</td>
            <td class="numeric mono">{job.connects_required}</td>
            <td class="numeric mono">{job.roi_score === null ? '-' : job.roi_score.toFixed(1)}</td>
            <td class={statusClass(job.status)}>{job.status}</td>
            <td class="mono">{job.scraped_at}</td>
          </tr>
        {:else}
          <tr>
            <td colspan="9" class="empty-table">No jobs.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>
