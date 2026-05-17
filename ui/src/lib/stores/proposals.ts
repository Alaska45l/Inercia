import { derived, get, writable } from 'svelte/store';

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'submitted';
export type FilterMode = 'all' | ProposalStatus;

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

type ServerMessage =
  | { type: 'proposal_ready'; data: Proposal }
  | { type: 'stats_update'; data: Stats }
  | { type: 'connects_balance'; data: ConnectsBalance }
  | { type: 'user_approved_ack'; data: { proposal_id: number } }
  | { type: 'user_rejected_ack'; data: { proposal_id: number } }
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
export const connectionState = writable<'connecting' | 'connected' | 'offline'>('connecting');
export const lastError = writable<string>('');

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

function upsertProposal(incoming: Proposal): void {
  proposals.update((items) => {
    const index = items.findIndex((proposal) => proposal.proposal_id === incoming.proposal_id);
    if (index === -1) {
      return [incoming, ...items];
    }
    const next = [...items];
    next[index] = { ...next[index], ...incoming };
    return next;
  });
}

function handleMessage(message: ServerMessage): void {
  if (message.type === 'proposal_ready') {
    upsertProposal(message.data);
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
    updateProposal(message.data.proposal_id, { status: 'approved' });
    return;
  }
  if (message.type === 'user_rejected_ack') {
    updateProposal(message.data.proposal_id, { status: 'rejected' });
    return;
  }
  if (message.type === 'error') {
    lastError.set(message.data.message);
  }
}

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;

export function connectProposalsSocket(url = 'ws://127.0.0.1:9741'): void {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  connectionState.set('connecting');
  socket = new WebSocket(url);
  socket.addEventListener('open', () => {
    connectionState.set('connected');
    lastError.set('');
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

export const proposalCounts = derived(proposals, ($proposals) => ({
  all: $proposals.length,
  pending: $proposals.filter((proposal) => proposal.status === 'pending').length,
  approved: $proposals.filter((proposal) => proposal.status === 'approved').length,
  rejected: $proposals.filter((proposal) => proposal.status === 'rejected').length
}));

export function currentProposal(proposalId: number): Proposal | undefined {
  return get(proposals).find((proposal) => proposal.proposal_id === proposalId);
}
