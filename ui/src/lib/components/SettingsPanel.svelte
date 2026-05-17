<script lang="ts">
  import { connects, setSetting, settingsState, updateConnectsTotal } from '../stores/proposals';

  function blurSetting(event: FocusEvent, key: string): void {
    const input = event.currentTarget as HTMLInputElement;
    setSetting(key, input.value);
  }

  function changeNetwork(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    setSetting('ALLOW_UPWORK_NETWORK', input.checked ? 'true' : 'false');
  }

  function blurConnects(event: FocusEvent): void {
    const input = event.currentTarget as HTMLInputElement;
    updateConnectsTotal(Number(input.value));
  }
</script>

<section class="settings-panel">
  {#if $settingsState}
    <section class="settings-section">
      <dl class="system-info">
        <dt>DB PATH</dt>
        <dd>{$settingsState.db_path}</dd>
        <dt>SESSION DIR</dt>
        <dd>{$settingsState.upwork_session_dir}</dd>
        <dt>WS PORT</dt>
        <dd>{$settingsState.ws_port}</dd>
        <dt>GEMINI KEY</dt>
        <dd class={$settingsState.has_gemini_key ? 'key-ok' : 'key-err'}>{$settingsState.has_gemini_key ? '✓' : '✗'}</dd>
        <dt>OPENCODE KEY</dt>
        <dd class={$settingsState.has_opencode_key ? 'key-ok' : 'key-err'}>{$settingsState.has_opencode_key ? '✓' : '✗'}</dd>
      </dl>
    </section>

    <section class="settings-section runtime-section">
      <div class="setting-row">
        <label for="daily-cap">DAILY CAP</label>
        <input
          id="daily-cap"
          class="control-input compact"
          type="number"
          min="1"
          max="50"
          value={$settingsState.daily_proposal_cap}
          on:blur={(event) => blurSetting(event, 'DAILY_PROPOSAL_CAP')}
        />
        <span>{$settingsState.daily_proposal_cap}</span>
      </div>

      <div class="setting-row">
        <label for="floor-hourly">FLOOR HOURLY $</label>
        <input
          id="floor-hourly"
          class="control-input compact"
          type="number"
          min="0"
          step="1"
          value={$settingsState.floor_hourly_rate}
          on:blur={(event) => blurSetting(event, 'FLOOR_HOURLY_RATE')}
        />
        <span>{$settingsState.floor_hourly_rate}</span>
      </div>

      <div class="setting-row">
        <label for="floor-fixed">FLOOR FIXED $</label>
        <input
          id="floor-fixed"
          class="control-input compact"
          type="number"
          min="0"
          step="5"
          value={$settingsState.floor_fixed_rate}
          on:blur={(event) => blurSetting(event, 'FLOOR_FIXED_RATE')}
        />
        <span>{$settingsState.floor_fixed_rate}</span>
      </div>

      <div class="setting-row">
        <span class="setting-label">LIVE NETWORK</span>
        <label class="toggle-row">
          <input
            type="checkbox"
            aria-label="Live network"
            checked={$settingsState.allow_upwork_network}
            on:change={changeNetwork}
          />
          <span class="toggle-visual" aria-hidden="true"></span>
        </label>
        <span>{$settingsState.allow_upwork_network ? 'true' : 'false'}</span>
      </div>

      <div class="setting-row">
        <label for="connects-total">CONNECTS TOTAL</label>
        <input
          id="connects-total"
          class="control-input compact"
          type="number"
          min="0"
          value={$connects.total}
          on:blur={blurConnects}
        />
        <span>{$connects.total}</span>
      </div>

      <p class="settings-note">Overrides stored in DB sessions table. Restart not required.</p>
    </section>
  {:else}
    <div class="status-line">Settings unavailable.</div>
  {/if}
</section>
