import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

interface JwtPayload {
  sub: string;
  role: string;
  tenant_slug: string;
  exp: number;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly TOKEN_KEY = 'cs_token';
  private readonly TENANT_KEY = 'cs_tenant';

  isLoggedIn = signal(this.hasValidToken());

  constructor(private http: HttpClient, private router: Router) {}

  login(email: string, password: string, tenantSlug: string) {
    return this.http
      .post<{ access_token: string; token_type: string }>(
        `${environment.apiUrl}/api/v1/agents/login`,
        { email, password },
        { headers: { 'X-Tenant-ID': tenantSlug } }
      )
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          localStorage.setItem(this.TENANT_KEY, tenantSlug);
          this.isLoggedIn.set(true);
        })
      );
  }

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.TENANT_KEY);
    this.isLoggedIn.set(false);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getTenantSlug(): string {
    return localStorage.getItem(this.TENANT_KEY) ?? '';
  }

  getPayload(): JwtPayload | null {
    const token = this.getToken();
    if (!token) return null;
    try {
      return JSON.parse(atob(token.split('.')[1]));
    } catch {
      return null;
    }
  }

  getAgentId(): string {
    return this.getPayload()?.sub ?? '';
  }

  getRole(): string {
    return this.getPayload()?.role ?? '';
  }

  isAdmin(): boolean {
    const role = this.getRole();
    return role === 'admin' || role === 'superadmin';
  }

  private hasValidToken(): boolean {
    const token = this.getToken();
    if (!token) return false;
    try {
      const payload: JwtPayload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp * 1000 > Date.now();
    } catch {
      return false;
    }
  }
}
