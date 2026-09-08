import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface AgentMetricRow {
  agent_id: string;
  name: string;
  email: string;
  status: 'online' | 'offline';
  active: boolean;
  assigned_conversations: number;
  handled_conversations: number;
  closed_conversations: number;
  active_conversations: number;
  released_conversations: number;
  human_messages: number;
  unread_messages: number;
  avg_first_response_seconds: number | null;
  avg_response_seconds: number | null;
  avg_resolution_seconds: number | null;
  first_response_samples: number;
  response_samples: number;
  resolution_samples: number;
}

export interface DailyAgentMetric {
  day: string;
  assigned_conversations: number;
  closed_conversations: number;
  human_messages: number;
}

export interface AgentMetricsResponse {
  from_date: string;
  to_date: string;
  agents: AgentMetricRow[];
  daily: DailyAgentMetric[];
}

@Injectable({ providedIn: 'root' })
export class AgentMetricsService {
  constructor(private http: HttpClient) {}

  getMetrics(from: string, to: string, agentId?: string) {
    let params = new HttpParams().set('from', from).set('to', to);
    if (agentId) params = params.set('agent_id', agentId);
    return this.http.get<AgentMetricsResponse>(
      `${environment.apiUrl}/api/v1/agent-metrics`,
      { params }
    );
  }
}
