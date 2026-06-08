<script lang="ts">
  import {
    checkUpworkSession,
    closeUpworkLogin,
    loginBrowserOpen,
    loginStatus,
    openUpworkLogin
  } from '../stores/proposals';
</script>

<section class="login-panel">
  {#if $loginBrowserOpen}
    <button class="control-button login-cancel" type="button" on:click={closeUpworkLogin}>Cancel Login</button>
    <div class="login-state">
      <span class="blink-dot" aria-hidden="true"></span>
      <span>{$loginStatus.message}</span>
    </div>
    <p>Close the browser after Find Work finishes loading.</p>
  {:else}
    <div class="login-actions">
      <button class="control-button" type="button" on:click={openUpworkLogin}>Open Upwork Login Browser</button>
      <button class="control-button" type="button" on:click={checkUpworkSession}>Check Session</button>
    </div>
    <p class:login-ok={$loginStatus.state === 'confirmed'} class:login-err={$loginStatus.state === 'failed'}>
      {$loginStatus.message}
    </p>
    <p>A visible Chromium window will open.<br />Login is verified after you close it.</p>
  {/if}
</section>
