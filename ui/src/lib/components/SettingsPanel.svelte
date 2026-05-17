<script lang="ts">
  import {
    connects,
    setJsonSetting,
    setSetting,
    settingsState,
    updateConnectsTotal
  } from '../stores/proposals';
  import type { UpworkSearchFilters } from '../stores/proposals';

  const categoryOptions = [
    'Web Development',
    'Software Development',
    'Scripts & Utilities',
    'Desktop Application Development',
    'Ecommerce Development'
  ];
  const experienceOptions = ['Entry', 'Intermediate', 'Expert'];
  const jobTypeOptions = ['Hourly', 'Fixed'];
  const hoursOptions = ['Less than 30', 'More than 30'];
  const projectLengthOptions = ['Less than 1 month', '1-3 months', '3-6 months', 'More than 6 months'];
  const clientHistoryOptions = ['No hires', '1-9 hires', '10+ hires'];
  const proposalOptions = ['Less than 5', '5-10', '10-15', '15-20', '20-50'];

  let blacklistDraft = '';
  let categoryDraft = categoryOptions[0];
  let attachmentDraft = '';

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

  function saveBlacklist(keywords: string[]): void {
    const cleaned = Array.from(new Set(keywords.map((item) => item.trim().toLowerCase()).filter(Boolean)));
    setJsonSetting('blacklist_keywords', cleaned);
  }

  function addBlacklistKeyword(): void {
    if (!$settingsState || !blacklistDraft.trim()) return;
    saveBlacklist([...$settingsState.blacklist_keywords, blacklistDraft]);
    blacklistDraft = '';
  }

  function removeBlacklistKeyword(keyword: string): void {
    if (!$settingsState) return;
    saveBlacklist($settingsState.blacklist_keywords.filter((item) => item !== keyword));
  }

  function saveAttachments(paths: string[]): void {
    const cleaned = Array.from(new Set(paths.map((item) => item.trim()).filter(Boolean)));
    setJsonSetting('portfolio_attachments', cleaned);
  }

  function addAttachment(): void {
    if (!$settingsState || !attachmentDraft.trim()) return;
    saveAttachments([...$settingsState.portfolio_attachments, attachmentDraft]);
    attachmentDraft = '';
  }

  function removeAttachment(path: string): void {
    if (!$settingsState) return;
    saveAttachments($settingsState.portfolio_attachments.filter((item) => item !== path));
  }

  function updateFilters(patch: Partial<UpworkSearchFilters>): void {
    if (!$settingsState) return;
    setJsonSetting('upwork_search_filters', { ...$settingsState.upwork_search_filters, ...patch });
  }

  function toggleFilterArray(key: keyof UpworkSearchFilters, value: string, checked: boolean): void {
    if (!$settingsState) return;
    const current = $settingsState.upwork_search_filters[key];
    if (!Array.isArray(current)) return;
    updateFilters({ [key]: checked ? [...current, value] : current.filter((item) => item !== value) });
  }

  function updateNumberFilter(event: FocusEvent, key: keyof UpworkSearchFilters): void {
    const input = event.currentTarget as HTMLInputElement;
    updateFilters({ [key]: input.value === '' ? null : Number(input.value) });
  }

  function updateTextFilter(event: FocusEvent, key: keyof UpworkSearchFilters): void {
    const input = event.currentTarget as HTMLInputElement;
    updateFilters({ [key]: input.value });
  }

  function addCategory(): void {
    if (!$settingsState || !categoryDraft.trim()) return;
    const categories = $settingsState.upwork_search_filters.categories;
    if (!categories.includes(categoryDraft)) updateFilters({ categories: [...categories, categoryDraft] });
  }

  function removeCategory(category: string): void {
    if (!$settingsState) return;
    updateFilters({
      categories: $settingsState.upwork_search_filters.categories.filter((item) => item !== category)
    });
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
      </dl>
    </section>

    <section class="settings-section runtime-section">
      <h3 class="settings-heading">Runtime</h3>
      <div class="setting-row">
        <label for="gemini-key">GEMINI API KEY</label>
        <input id="gemini-key" class="control-input" type="password" value={$settingsState.gemini_api_key} on:blur={(event) => blurSetting(event, 'GEMINI_API_KEY')} />
        <span class={$settingsState.has_gemini_key ? 'key-ok' : 'key-err'}>{$settingsState.has_gemini_key ? 'set' : 'missing'}</span>
      </div>
      <div class="setting-row">
        <label for="opencode-key">OPENCODE API KEY</label>
        <input id="opencode-key" class="control-input" type="password" value={$settingsState.opencode_api_key} on:blur={(event) => blurSetting(event, 'OPENCODE_API_KEY')} />
        <span class={$settingsState.has_opencode_key ? 'key-ok' : 'key-err'}>{$settingsState.has_opencode_key ? 'set' : 'missing'}</span>
      </div>
      <div class="setting-row">
        <label for="opencode-url">OPENCODE URL</label>
        <input id="opencode-url" class="control-input" type="text" value={$settingsState.opencode_base_url} on:blur={(event) => blurSetting(event, 'OPENCODE_BASE_URL')} />
        <span>editable</span>
      </div>
      <div class="setting-row">
        <label for="opencode-model">COPYWRITER MODEL</label>
        <input id="opencode-model" class="control-input" type="text" value={$settingsState.opencode_copywriter_model} on:blur={(event) => blurSetting(event, 'OPENCODE_COPYWRITER_MODEL')} />
        <span>editable</span>
      </div>
      <div class="setting-row">
        <label for="opencode-agent">OPENCODE AGENT</label>
        <input id="opencode-agent" class="control-input" type="text" value={$settingsState.opencode_user_agent} on:blur={(event) => blurSetting(event, 'OPENCODE_USER_AGENT')} />
        <span>editable</span>
      </div>
      <div class="setting-row">
        <label for="daily-cap">DAILY CAP</label>
        <input id="daily-cap" class="control-input compact" type="number" min="1" max="50" value={$settingsState.daily_proposal_cap} on:blur={(event) => blurSetting(event, 'DAILY_PROPOSAL_CAP')} />
        <span>{$settingsState.daily_proposal_cap}</span>
      </div>
      <div class="setting-row">
        <label for="floor-hourly">FLOOR HOURLY $</label>
        <input id="floor-hourly" class="control-input compact" type="number" min="0" step="1" value={$settingsState.floor_hourly_rate} on:blur={(event) => blurSetting(event, 'FLOOR_HOURLY_RATE')} />
        <span>{$settingsState.floor_hourly_rate}</span>
      </div>
      <div class="setting-row">
        <label for="floor-fixed">FLOOR FIXED $</label>
        <input id="floor-fixed" class="control-input compact" type="number" min="0" step="5" value={$settingsState.floor_fixed_rate} on:blur={(event) => blurSetting(event, 'FLOOR_FIXED_RATE')} />
        <span>{$settingsState.floor_fixed_rate}</span>
      </div>
      <div class="setting-row">
        <span class="setting-label">LIVE NETWORK</span>
        <label class="toggle-row">
          <input type="checkbox" aria-label="Live network" checked={$settingsState.allow_upwork_network} on:change={changeNetwork} />
          <span class="toggle-visual" aria-hidden="true"></span>
        </label>
        <span>{$settingsState.allow_upwork_network ? 'true' : 'false'}</span>
      </div>
      <div class="setting-row">
        <label for="scheduler-min">MIN INTERVAL</label>
        <input id="scheduler-min" class="control-input compact" type="number" min="1" value={$settingsState.scheduler_interval_min_minutes} on:blur={(event) => blurSetting(event, 'SCHEDULER_INTERVAL_MIN_MINUTES')} />
        <span>minutes</span>
      </div>
      <div class="setting-row">
        <label for="scheduler-max">MAX INTERVAL</label>
        <input id="scheduler-max" class="control-input compact" type="number" min="1" value={$settingsState.scheduler_interval_max_minutes} on:blur={(event) => blurSetting(event, 'SCHEDULER_INTERVAL_MAX_MINUTES')} />
        <span>minutes</span>
      </div>
      <div class="setting-row">
        <label for="connects-total">CONNECTS TOTAL</label>
        <input id="connects-total" class="control-input compact" type="number" min="0" value={$connects.total} on:blur={blurConnects} />
        <span>{$connects.total}</span>
      </div>
    </section>

    <section class="settings-section filter-settings">
      <h3 class="settings-heading">Upwork Filters</h3>
      <div class="setting-row">
        <label for="category-picker">CATEGORY</label>
        <select id="category-picker" class="control-input" bind:value={categoryDraft}>
          {#each categoryOptions as category}
            <option value={category}>{category}</option>
          {/each}
        </select>
        <button class="inline-button" type="button" on:click={addCategory}>Add</button>
      </div>
      <div class="chip-list">
        {#each $settingsState.upwork_search_filters.categories as category}
          <button type="button" class="chip-button" on:click={() => removeCategory(category)}>{category} x</button>
        {/each}
      </div>

      <div class="checkbox-grid">
        <fieldset>
          <legend>Experience</legend>
          {#each experienceOptions as option}
            <label><input type="checkbox" checked={$settingsState.upwork_search_filters.experience_levels.includes(option)} on:change={(event) => toggleFilterArray('experience_levels', option, (event.currentTarget as HTMLInputElement).checked)} /> {option}</label>
          {/each}
        </fieldset>
        <fieldset>
          <legend>Job Type</legend>
          {#each jobTypeOptions as option}
            <label><input type="checkbox" checked={$settingsState.upwork_search_filters.job_types.includes(option)} on:change={(event) => toggleFilterArray('job_types', option, (event.currentTarget as HTMLInputElement).checked)} /> {option}</label>
          {/each}
        </fieldset>
        <fieldset>
          <legend>Project Length</legend>
          {#each projectLengthOptions as option}
            <label><input type="checkbox" checked={$settingsState.upwork_search_filters.project_lengths.includes(option)} on:change={(event) => toggleFilterArray('project_lengths', option, (event.currentTarget as HTMLInputElement).checked)} /> {option}</label>
          {/each}
        </fieldset>
      </div>

      <div class="settings-grid">
        <label>Fixed min<input class="control-input compact" type="number" min="0" value={$settingsState.upwork_search_filters.budget_min ?? ''} on:blur={(event) => updateNumberFilter(event, 'budget_min')} /></label>
        <label>Fixed max<input class="control-input compact" type="number" min="0" value={$settingsState.upwork_search_filters.budget_max ?? ''} on:blur={(event) => updateNumberFilter(event, 'budget_max')} /></label>
        <label>Hourly min<input class="control-input compact" type="number" min="0" value={$settingsState.upwork_search_filters.hourly_rate_min ?? ''} on:blur={(event) => updateNumberFilter(event, 'hourly_rate_min')} /></label>
        <label>Hourly max<input class="control-input compact" type="number" min="0" value={$settingsState.upwork_search_filters.hourly_rate_max ?? ''} on:blur={(event) => updateNumberFilter(event, 'hourly_rate_max')} /></label>
        <label>Max connects<input class="control-input compact" type="number" min="0" value={$settingsState.upwork_search_filters.max_connects} on:blur={(event) => updateNumberFilter(event, 'max_connects')} /></label>
        <label>Client location<input class="control-input" type="text" value={$settingsState.upwork_search_filters.client_location} on:blur={(event) => updateTextFilter(event, 'client_location')} /></label>
      </div>

      <div class="checkbox-grid">
        <fieldset>
          <legend>Hours/week</legend>
          {#each hoursOptions as option}
            <label><input type="checkbox" checked={$settingsState.upwork_search_filters.hours_per_week.includes(option)} on:change={(event) => toggleFilterArray('hours_per_week', option, (event.currentTarget as HTMLInputElement).checked)} /> {option}</label>
          {/each}
        </fieldset>
        <fieldset>
          <legend>Client history</legend>
          {#each clientHistoryOptions as option}
            <label><input type="checkbox" checked={$settingsState.upwork_search_filters.client_history.includes(option)} on:change={(event) => toggleFilterArray('client_history', option, (event.currentTarget as HTMLInputElement).checked)} /> {option}</label>
          {/each}
        </fieldset>
        <fieldset>
          <legend>Proposals</legend>
          {#each proposalOptions as option}
            <label><input type="checkbox" checked={$settingsState.upwork_search_filters.proposals.includes(option)} on:change={(event) => toggleFilterArray('proposals', option, (event.currentTarget as HTMLInputElement).checked)} /> {option}</label>
          {/each}
        </fieldset>
      </div>
    </section>

    <section class="settings-section">
      <h3 class="settings-heading">Blacklist Keywords</h3>
      <div class="add-row">
        <input class="control-input" type="text" bind:value={blacklistDraft} on:keydown={(event) => event.key === 'Enter' && addBlacklistKeyword()} />
        <button class="inline-button" type="button" on:click={addBlacklistKeyword}>Add</button>
      </div>
      <div class="chip-list">
        {#each $settingsState.blacklist_keywords as keyword}
          <button type="button" class="chip-button" on:click={() => removeBlacklistKeyword(keyword)}>{keyword} x</button>
        {/each}
      </div>
    </section>

    <section class="settings-section">
      <h3 class="settings-heading">Portfolio Attachments</h3>
      <div class="add-row">
        <input class="control-input" type="text" bind:value={attachmentDraft} placeholder="/absolute/path/to/sample.pdf" on:keydown={(event) => event.key === 'Enter' && addAttachment()} />
        <button class="inline-button" type="button" on:click={addAttachment}>Add</button>
      </div>
      <div class="path-list">
        {#each $settingsState.portfolio_attachments as path}
          <button type="button" class="chip-button path-chip" on:click={() => removeAttachment(path)}>{path} x</button>
        {/each}
      </div>
    </section>
  {:else}
    <div class="status-line">Settings unavailable.</div>
  {/if}
</section>
