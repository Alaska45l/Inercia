<script lang="ts">
  import type { ConnectsBalance } from '../stores/proposals';

  export let balance: ConnectsBalance;

  $: total = Math.max(balance.total, 1);
  $: spent = Math.min(balance.spent_today, total);
  $: remaining = Math.max(balance.remaining, 0);
  $: percent = Math.round((remaining / total) * 100);
  $: stroke = 2 * Math.PI * 42;
  $: dashOffset = stroke - (percent / 100) * stroke;
</script>

<section class="panel connects-panel" aria-label="Connects tracker">
  <div class="ring-wrap">
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <circle class="ring-bg" cx="50" cy="50" r="42" />
      <circle class="ring-fg" cx="50" cy="50" r="42" style={`stroke-dasharray: ${stroke}; stroke-dashoffset: ${dashOffset}`} />
    </svg>
    <div class="ring-copy">
      <strong>{remaining}</strong>
      <span>left</span>
    </div>
  </div>
  <div class="connects-meta">
    <div><span>Total</span><strong>{balance.total}</strong></div>
    <div><span>Spent</span><strong>{spent}</strong></div>
    <div><span>Remaining</span><strong>{remaining}</strong></div>
  </div>
</section>
