<script lang="ts">
  import { closeUpworkLogin, loginBrowserOpen, openUpworkLogin } from '../stores/proposals';
</script>

<section class="login-panel">
  {#if $loginBrowserOpen}
    <button class="control-button login-open" type="button" on:click={closeUpworkLogin}>Close Browser</button>
    <div class="login-state">
      <span class="blink-dot" aria-hidden="true"></span>
      <span>Browser open — waiting for login</span>
    </div>
  {:else}
    <button class="control-button" type="button" on:click={openUpworkLogin}>Open Upwork Login Browser</button>
    <p>A visible Chromium window will open.<br />Log in manually, then click Close Browser.</p>
  {/if}
</section>
