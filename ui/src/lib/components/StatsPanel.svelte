<script lang="ts">
  import type { Stats } from '../stores/proposals';

  export let stats: Stats;
</script>

<section class="stats-panel" aria-label="Today stats">
  <div class="stats-grid">
    <div>
      <strong>{stats.today_submitted}</strong>
      <span>Submitted</span>
    </div>
    <div>
      <strong>{stats.today_approved}</strong>
      <span>Approved</span>
    </div>
    <div>
      <strong>{stats.today_rejected}</strong>
      <span>Rejected</span>
    </div>
  </div>
</section>
