import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SuperadminUser } from '../models/superadmin.model';
import { SuperadminAuthService } from './superadmin-auth.service';
import { TenantOut, TenantCreate, TenantUpdate } from '../models/tenant.model';

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
}
