import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

interface LoginResponse {
  access_token: string;
  role: string;
  nombre: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly TOKEN_KEY = 'adm_token';
  private readonly USER_KEY  = 'adm_user';

  constructor(private http: HttpClient, private router: Router) {}

  login(usuario: string, clave: string) {
    return this.http.post<LoginResponse>(`${environment.apiUrl}/admin/auth/login`, { usuario, clave })
      .pipe(tap(res => {
        localStorage.setItem(this.TOKEN_KEY, res.access_token);
        localStorage.setItem(this.USER_KEY, JSON.stringify({ role: res.role, nombre: res.nombre }));
      }));
  }

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  getUser(): { role: string; nombre: string } | null {
    const raw = localStorage.getItem(this.USER_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  getRole(): string {
    return this.getUser()?.role ?? '';
  }

  isAdmin(): boolean { return this.getRole() === 'admin'; }
  canEdit(): boolean { return ['admin', 'edit'].includes(this.getRole()); }
}
