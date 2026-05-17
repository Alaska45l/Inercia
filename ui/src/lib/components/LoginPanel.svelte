<script lang="ts">
  import { closeUpworkLogin, loginBrowserOpen, loginStatus, openUpworkLogin } from '../stores/proposals';
</script>

<section class="login-panel">
  {#if $loginBrowserOpen}
    <button class="control-button login-open" type="button" on:click={closeUpworkLogin}>Confirm Login</button>
    <div class="login-state">
      <span class="blink-dot" aria-hidden="true"></span>
      <span>{$loginStatus.message}</span>
    </div>
  {:else}
    <button class="control-button" type="button" on:click={openUpworkLogin}>Open Upwork Login Browser</button>
    <p class:login-ok={$loginStatus.state === 'confirmed'} class:login-err={$loginStatus.state === 'failed'}>
      {$loginStatus.message}
    </p>
    <p>A visible Chromium window will open.<br />Log in manually, then click Confirm Login.</p>
  {/if}
</section>
