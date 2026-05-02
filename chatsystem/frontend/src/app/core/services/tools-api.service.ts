import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export type ToolType = 'HTTP' | 'SQL' | 'STATIC';

export interface AgentTool {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  tool_type: ToolType;
  enabled: boolean;
  http_url: string | null;
  http_method: string | null;
  http_headers: Record<string, string> | null;
  http_body_tpl: string | null;
  http_timeout_seconds: number | null;
  sql_dsn: string | null;
  sql_query: string | null;
  sql_params: string[] | null;
  static_text: string | null;
  created_at: string;
  updated_at: string;
}

export type AgentToolCreate = Omit<AgentTool, 'id' | 'tenant_id' | 'created_at' | 'updated_at'>;
export type AgentToolUpdate = Partial<AgentToolCreate>;

export interface TestToolRequest {
  params: Record<string, string>;
}

@Injectable({ providedIn: 'root' })
export class ToolsApiService {
  private base = `${environment.apiUrl}/api/v1/tools`;

  constructor(private http: HttpClient) {}

  list() {
    return this.http.get<AgentTool[]>(this.base);
  }

  create(data: AgentToolCreate) {
    return this.http.post<AgentTool>(this.base, data);
  }

  update(id: string, data: AgentToolUpdate) {
    return this.http.put<AgentTool>(`${this.base}/${id}`, data);
  }

  delete(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  test(id: string, params: Record<string, string>) {
    return this.http.post<{ result: string }>(`${this.base}/${id}/test`, { params });
  }
}
