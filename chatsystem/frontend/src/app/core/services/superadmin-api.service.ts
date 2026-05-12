import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SuperadminUser } from '../models/superadmin.model';
import { SuperadminAuthService } from './superadmin-auth.service';
import { TenantOut, TenantCreate, TenantUpdate } from '../models/tenant.model';

export interface TokenUsageRow {
  tenant_id?: string;
  tenant_name?: string;
  tenant_slug?: string;
  year: number;
  month: number;
  tokens_in: number;
  tokens_out: number;
  tokens_total: number;
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class SuperadminApiService {
  private base = `${environment.apiUrl}/api/v1`;

  constructor(private http: HttpClient, private saAuth: SuperadminAuthService) {}

  private headers(): HttpHeaders {
    return new HttpHeaders({ Authorization: `Bearer ${this.saAuth.getToken() ?? ''}` });
  }

  // ── Superadmin users ──────────────────────────────────────────────────────

  getMe(): Observable<SuperadminUser> {
    return this.http.get<SuperadminUser>(`${this.base}/superadmin/me`, { headers: this.headers() });
  }

  listUsers(): Observable<SuperadminUser[]> {
    return this.http.get<SuperadminUser[]>(`${this.base}/superadmin/users`, { headers: this.headers() });
  }

  createUser(data: { email: string; name: string; password: string }): Observable<SuperadminUser> {
    return this.http.post<SuperadminUser>(`${this.base}/superadmin/users`, data, { headers: this.headers() });
  }

  deleteUser(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/superadmin/users/${id}`, { headers: this.headers() });
  }

  // ── Tenants ───────────────────────────────────────────────────────────────

  listTenants(): Observable<TenantOut[]> {
    return this.http.get<TenantOut[]>(`${this.base}/tenants`, { headers: this.headers() });
  }

  createTenant(data: TenantCreate): Observable<TenantOut> {
    return this.http.post<TenantOut>(`${this.base}/tenants`, data, { headers: this.headers() });
  }

  updateTenant(id: string, data: TenantUpdate): Observable<TenantOut> {
    return this.http.put<TenantOut>(`${this.base}/tenants/${id}`, data, { headers: this.headers() });
  }

  // ── Knowledge base ────────────────────────────────────────────────────────

  uploadKnowledge(tenantId: string, text: string): Observable<{ tenant_id: string; chunks: number }> {
    return this.http.post<{ tenant_id: string; chunks: number }>(
      `${this.base}/knowledge/${tenantId}/upload`,
      { text },
      { headers: this.headers() },
    );
  }

  deleteKnowledge(tenantId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/knowledge/${tenantId}`, { headers: this.headers() });
  }

  getKnowledgeStatus(tenantId: string): Observable<{ tenant_id: string; chunks: number; has_knowledge: boolean }> {
    return this.http.get<{ tenant_id: string; chunks: number; has_knowledge: boolean }>(
      `${this.base}/knowledge/${tenantId}/status`,
      { headers: this.headers() },
    );
  }

  // ── Token usage ───────────────────────────────────────────────────────────

  getTokenUsageAll(year?: number, month?: number): Observable<TokenUsageRow[]> {
    let params = new HttpParams();
    if (year != null)  params = params.set('year',  year);
    if (month != null) params = params.set('month', month);
    return this.http.get<TokenUsageRow[]>(`${this.base}/token-usage/all`, {
      headers: this.headers(), params,
    });
  }

  getTokenUsageTenant(tenantId: string, months = 6): Observable<TokenUsageRow[]> {
    const params = new HttpParams().set('months', months);
    return this.http.get<TokenUsageRow[]>(`${this.base}/token-usage/${tenantId}`, {
      headers: this.headers(), params,
    });
  }
}
