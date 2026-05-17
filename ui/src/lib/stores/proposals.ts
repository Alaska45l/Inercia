import { derived, get, writable } from 'svelte/store';

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'submitted';
export type FilterMode = 'all' | ProposalStatus;
export type Panel = 'proposals' | 'scraper' | 'jobs' | 'settings';

export interface Proposal {
  proposal_id: number;
  job_id: number;
  upwork_id: string;
  title: string;
  client_country: string | null;
  roi_score: number;
  connects_cost: number;
  bid_rate: number;
  bid_type: 'hourly' | 'fixed' | string;
  cover_letter: string;
  screening_answers: Record<string, string>;
  cv_pdf_path: string | null;
  status: ProposalStatus;
}

export interface Stats {
  today_submitted: number;
  today_approved: number;
  today_rejected: number;
  connects_remaining: number;
  connects_spent_today: number;
}

export interface ConnectsBalance {
  total: number;
  spent_today: number;
  remaining: number;
}

export interface JobRow {
  id: number;
  upwork_id: string;
  title: string;
  job_type: 'hourly' | 'fixed';
  roi_score: number | null;
  status: string;
  scraped_at: string;
}

export interface UpworkSearchFilters {
  categories: string[];
  experience_levels: string[];
  job_types: string[];
  budget_min: number | null;
  budget_max: number | null;
  hourly_rate_min: number | null;
  hourly_rate_max: number | null;
  hours_per_week: string[];
  project_lengths: string[];
  client_history: string[];
  client_location: string;
  proposals: string[];
  max_connects: number;
}

export interface SettingsState {
  gemini_api_key: string;
  opencode_api_key: string;
  opencode_base_url: string;
  opencode_copywriter_model: string;
  opencode_user_agent: string;
  daily_proposal_cap: number;
  floor_hourly_rate: number;
  floor_fixed_rate: number;
  allow_upwork_network: boolean;
  db_path: string;
  upwork_session_dir: string;
  ws_port: number;
  has_gemini_key: boolean;
  has_opencode_key: boolean;
  scheduler_interval_min_minutes: number;
  scheduler_interval_max_minutes: number;
  blacklist_keywords: string[];
  upwork_search_filters: UpworkSearchFilters;
  portfolio_attachments: string[];
}

export interface SchedulerStatus {
  running: boolean;
  next_run_in_seconds: number;
}

type ServerMessage =
  | { type: 'proposal_ready'; data: Proposal }
  | { type: 'stats_update'; data: Stats }
  | { type: 'connects_balance'; data: ConnectsBalance }
  | { type: 'user_approved_ack'; data: { proposal_id: number } }
  | { type: 'user_rejected_ack'; data: { proposal_id: number } }
  | { type: 'scrape_progress'; data: { phase: string; queued: number; processed: number; failed: number } }
  | { type: 'scrape_done'; data: { query: string; queued: number; processed: number; inserted: number; failed: number } }
  | { type: 'process_progress'; data: { processed: number; ready: number; blacklisted: number; failed: number } }
  | {
      type: 'process_done';
      data: { processed: number; ready: number; blacklisted: number; failed: number; cap_reached: boolean };
    }
  | { type: 'jobs_list'; data: { jobs: JobRow[] } }
  | { type: 'settings_state'; data: SettingsState }
  | { type: 'scheduler_status'; data: SchedulerStatus }
  | { type: 'login_browser_opened' }
  | { type: 'login_browser_closed' }
  | { type: 'error'; data: { message: string } };

export const proposals = writable<Proposal[]>([]);
export const stats = writable<Stats>({
  today_submitted: 0,
  today_approved: 0,
  today_rejected: 0,
  connects_remaining: 211,
  connects_spent_today: 0
});
export const connects = writable<ConnectsBalance>({ total: 211, spent_today: 0, remaining: 211 });
export const filterMode = writable<FilterMode>('all');
export const activePanel = writable<Panel>('proposals');
export const connectionState = writable<'connecting' | 'connected' | 'offline'>('connecting');
export const lastError = writable<string>('');
export const jobs = writable<JobRow[]>([]);
export const settingsState = writable<SettingsState | null>(null);
export const schedulerStatus = writable<SchedulerStatus>({ running: false, next_run_in_seconds: 0 });
export const scrapeRunning = writable(false);
export const processRunning = writable(false);
export const loginBrowserOpen = writable(false);
export const lastScrapeResult = writable<string>('');
export const lastProcessResult = writable<string>('');

export const filteredProposals = derived([proposals, filterMode], ([$proposals, $filterMode]) => {
  if ($filterMode === 'all') {
    return $proposals;
  }
  return $proposals.filter((proposal) => proposal.status === $filterMode);
});

export function updateProposal(id: number, patch: Partial<Proposal>): void {
  proposals.update((items) =>
    items.map((proposal) => (proposal.proposal_id === id ? { ...proposal, ...patch } : proposal))
  );
}

function upsertProposal(incoming: Proposal): boolean {
  let inserted = false;
  proposals.update((items) => {
    const index = items.findIndex((proposal) => proposal.proposal_id === incoming.proposal_id);
    if (index === -1) {
      inserted = true;
      return [incoming, ...items];
    }
    const next = [...items];
    next[index] = { ...next[index], ...incoming };
    return next;
  });
  return inserted;
}

function playNotificationSound(): void {
  const audio = new Audio('/notification.wav');
  audio.play().catch(() => undefined);
}

function notifyProposalReady(proposal: Proposal): void {
  playNotificationSound();
  if (!('Notification' in window)) return;
  const show = () => {
    new Notification('Inercia — New Proposal Ready', {
      body: `${proposal.title} — ROI ${proposal.roi_score.toFixed(1)} — ${proposal.connects_cost} connects`
    });
  };
  if (Notification.permission === 'granted') {
    show();
    return;
  }
  if (Notification.permission === 'default') {
    Notification.requestPermission().then((permission) => {
      if (permission === 'granted') show();
    });
  }
}

function handleMessage(message: ServerMessage): void {
  if (message.type === 'proposal_ready') {
    const inserted = upsertProposal(message.data);
    if (initialLoadComplete && inserted && message.data.status === 'pending') notifyProposalReady(message.data);
    return;
  }
  if (message.type === 'stats_update') {
    stats.set(message.data);
    connects.update((current) => ({
      total: current.total,
      spent_today: message.data.connects_spent_today,
      remaining: message.data.connects_remaining
    }));
    return;
  }
  if (message.type === 'connects_balance') {
    connects.set(message.data);
    return;
  }
  if (message.type === 'user_approved_ack') {
    updateProposal(message.data.proposal_id, { status: 'submitted' });
    return;
  }
  if (message.type === 'user_rejected_ack') {
    updateProposal(message.data.proposal_id, { status: 'rejected' });
    return;
  }
  if (message.type === 'scrape_progress') {
    scrapeRunning.set(true);
    lastScrapeResult.set(`${message.data.phase} · queued ${message.data.queued} · processed ${message.data.processed}`);
    return;
  }
  if (message.type === 'scrape_done') {
    scrapeRunning.set(false);
    lastScrapeResult.set(
      `${message.data.query} · queued ${message.data.queued} · processed ${message.data.processed} · inserted ${message.data.inserted} · failed ${message.data.failed}`
    );
    return;
  }
  if (message.type === 'process_progress') {
    processRunning.set(true);
    lastProcessResult.set(
      `processed ${message.data.processed} · ready ${message.data.ready} · blacklisted ${message.data.blacklisted} · failed ${message.data.failed}`
    );
    return;
  }
  if (message.type === 'process_done') {
    processRunning.set(false);
    lastProcessResult.set(
      `processed ${message.data.processed} · ready ${message.data.ready} · blacklisted ${message.data.blacklisted} · failed ${message.data.failed}${message.data.cap_reached ? ' · cap reached' : ''}`
    );
    return;
  }
  if (message.type === 'jobs_list') {
    jobs.set(message.data.jobs);
    return;
  }
  if (message.type === 'settings_state') {
    settingsState.set(message.data);
    return;
  }
  if (message.type === 'scheduler_status') {
    schedulerStatus.set(message.data);
    initialLoadComplete = true;
    return;
  }
  if (message.type === 'login_browser_opened') {
    loginBrowserOpen.set(true);
    return;
  }
  if (message.type === 'login_browser_closed') {
    loginBrowserOpen.set(false);
    return;
  }
  if (message.type === 'error') {
    lastError.set(message.data.message);
    scrapeRunning.set(false);
    processRunning.set(false);
  }
}

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let initialLoadComplete = false;

export function connectProposalsSocket(url = 'ws://127.0.0.1:9741'): void {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  connectionState.set('connecting');
  socket = new WebSocket(url);
  socket.addEventListener('open', () => {
    connectionState.set('connected');
    lastError.set('');
    initialLoadComplete = false;
  });
  socket.addEventListener('message', (event) => {
    try {
      handleMessage(JSON.parse(String(event.data)) as ServerMessage);
    } catch (error) {
      lastError.set(error instanceof Error ? error.message : 'Invalid server message');
    }
  });
  socket.addEventListener('close', () => {
    connectionState.set('offline');
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
    }
    reconnectTimer = window.setTimeout(() => connectProposalsSocket(url), 1800);
  });
  socket.addEventListener('error', () => {
    lastError.set('WebSocket connection failed');
  });
}

function sendMessage(payload: object): void {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    lastError.set('WebSocket is not connected');
    return;
  }
  socket.send(JSON.stringify(payload));
}

export function approveProposal(proposalId: number): void {
  updateProposal(proposalId, { status: 'approved' });
  sendMessage({ type: 'user_approved', proposal_id: proposalId });
}

export function rejectProposal(proposalId: number, reason: string | null = null): void {
  updateProposal(proposalId, { status: 'rejected' });
  sendMessage({ type: 'user_rejected', proposal_id: proposalId, reason });
}

export function saveEditedLetter(proposalId: number, coverLetter: string): void {
  updateProposal(proposalId, { cover_letter: coverLetter });
}

export function runScrape(query: string, allowNetwork: boolean): void {
  scrapeRunning.set(true);
  sendMessage({ type: 'run_scrape', query, allow_network: allowNetwork });
}

export function runConfiguredScrape(): void {
  scrapeRunning.set(true);
  sendMessage({ type: 'run_scrape', query: '' });
}

export function runProcess(limit: number): void {
  processRunning.set(true);
  sendMessage({ type: 'run_process', limit });
}

export function openUpworkLogin(): void {
  sendMessage({ type: 'open_upwork_login' });
}

export function closeUpworkLogin(): void {
  sendMessage({ type: 'close_upwork_login' });
}

export function requestJobs(status: string | null = null, limit = 100): void {
  sendMessage({ type: 'get_jobs', status, limit });
}

export function requestSettings(): void {
  sendMessage({ type: 'get_settings' });
}

export function setSetting(key: string, value: string): void {
  sendMessage({ type: 'set_setting', key, value });
}

export function setJsonSetting(key: string, value: unknown): void {
  setSetting(key, JSON.stringify(value));
}

export function startScheduler(): void {
  sendMessage({ type: 'start_scheduler' });
}

export function stopScheduler(): void {
  sendMessage({ type: 'stop_scheduler' });
}

export function updateConnectsTotal(total: number): void {
  sendMessage({ type: 'set_connects_total', total });
}

export const proposalCounts = derived(proposals, ($proposals) => ({
  all: $proposals.length,
  pending: $proposals.filter((proposal) => proposal.status === 'pending').length,
  approved: $proposals.filter((proposal) => proposal.status === 'approved').length,
  rejected: $proposals.filter((proposal) => proposal.status === 'rejected').length
}));

export function currentProposal(proposalId: number): Proposal | undefined {
  return get(proposals).find((proposal) => proposal.proposal_id === proposalId);
}
