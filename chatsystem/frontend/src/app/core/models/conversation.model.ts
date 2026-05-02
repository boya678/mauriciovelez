export type ConversationStatus =
  | 'new'
  | 'bot_active'
  | 'waiting_human'
  | 'human_active'
  | 'closed';

export interface Conversation {
  id: string;
  phone: string;
  status: ConversationStatus;
  assigned_agent_id: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

import { Message } from './message.model';

export const STATUS_LABELS: Record<ConversationStatus, string> = {
  new: 'Nueva',
  bot_active: 'Bot activo',
  waiting_human: 'Esperando agente',
  human_active: 'Con agente',
  closed: 'Cerrada',
};

export const STATUS_BADGE: Record<ConversationStatus, string> = {
  new: 'badge-gray',
  bot_active: 'badge-blue',
  waiting_human: 'badge-yellow',
  human_active: 'badge-green',
  closed: 'badge-gray',
};
