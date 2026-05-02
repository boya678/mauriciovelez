export type AgentStatus = 'online' | 'offline';
export type AgentRole = 'agent' | 'admin' | 'superadmin';

export interface Agent {
  id: string;
  name: string;
  email: string;
  role: AgentRole;
  status: AgentStatus;
  max_concurrent_chats: number;
  tenant_id: string;
  created_at: string;
}

export interface AgentCreate {
  name: string;
  email: string;
  password: string;
  role: AgentRole;
  max_concurrent_chats: number;
}

export interface AgentUpdate {
  name?: string;
  email?: string;
  password?: string;
  role?: AgentRole;
  max_concurrent_chats?: number;
}
