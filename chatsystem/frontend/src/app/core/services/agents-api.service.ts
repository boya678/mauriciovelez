import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { Agent, AgentCreate, AgentStatus, AgentUpdate } from '../models/agent.model';
import { TokenUsageRow } from './superadmin-api.service';

export interface TenantSettings {
  ai_system_prompt: string | null;
  whatsapp_template_name: string | null;
  whatsapp_template_language: string | null;
}

export interface KnowledgeStatus {
  tenant_id: string;
  chunks: number;
  has_knowledge: boolean;
}

export interface KnowledgeUploadOut {
  tenant_id: string;
  chunks: number;
}

export interface MessageStatsRow {
  year: number;
  month: number;
  bot_messages: number;
  human_messages: number;
  user_messages: number;
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class AgentsApiService {
  constructor(private http: HttpClient) {}

  getMe() {
    return this.http.get<Agent>(`${environment.apiUrl}/api/v1/agents/me`);
  }

  setStatus(status: AgentStatus) {
    return this.http.put<Agent>(`${environment.apiUrl}/api/v1/agents/me/status`, { status });
  }

  heartbeat() {
    return this.http.post<{ ok: boolean }>(`${environment.apiUrl}/api/v1/agents/heartbeat`, {});
  }

  list() {
    return this.http.get<Agent[]>(`${environment.apiUrl}/api/v1/agents`);
  }

  create(data: AgentCreate) {
    return this.http.post<Agent>(`${environment.apiUrl}/api/v1/agents`, data);
  }

  update(id: string, data: AgentUpdate) {
    return this.http.put<Agent>(`${environment.apiUrl}/api/v1/agents/${id}`, data);
  }

  delete(id: string) {
    return this.http.delete<void>(`${environment.apiUrl}/api/v1/agents/${id}`);
  }

  getSettings() {
    return this.http.get<TenantSettings>(`${environment.apiUrl}/api/v1/agents/settings`);
  }

  updateSettings(data: TenantSettings) {
    return this.http.put<TenantSettings>(`${environment.apiUrl}/api/v1/agents/settings`, data);
  }

  getKnowledgeStatus() {
    return this.http.get<KnowledgeStatus>(`${environment.apiUrl}/api/v1/knowledge/my/status`);
  }

  uploadKnowledge(text: string) {
    return this.http.post<KnowledgeUploadOut>(`${environment.apiUrl}/api/v1/knowledge/my/upload`, { text });
  }

  deleteKnowledge() {
    return this.http.delete<void>(`${environment.apiUrl}/api/v1/knowledge/my`);
  }

  getTokenUsageMy(months = 6) {
    const params = new HttpParams().set('months', months);
    return this.http.get<TokenUsageRow[]>(`${environment.apiUrl}/api/v1/token-usage/my`, { params });
  }

  getMessageStatsMy(months = 6) {
    const params = new HttpParams().set('months', months);
    return this.http.get<MessageStatsRow[]>(`${environment.apiUrl}/api/v1/message-stats/my`, { params });
  }
}
