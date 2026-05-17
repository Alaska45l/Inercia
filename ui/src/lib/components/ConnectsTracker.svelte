<script lang="ts">
  import type { ConnectsBalance } from '../stores/proposals';

  export let balance: ConnectsBalance;

  $: total = Math.max(balance.total, 1);
  $: remaining = Math.max(balance.remaining, 0);
</script>

<section class="connects-panel" aria-label="Connects tracker">
  <p class="connects-line">{remaining} / {balance.total} connects</p>
  <progress value={remaining} max={total} aria-label={`${remaining} connects remaining`}></progress>
</section>
