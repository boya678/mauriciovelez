import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { Agent, AgentCreate, AgentStatus, AgentUpdate } from '../models/agent.model';

export interface TenantSettings {
  ai_system_prompt: string | null;
  whatsapp_template_name: string | null;
  whatsapp_template_language: string | null;
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
}
