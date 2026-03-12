import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface Cliente {
  id: string;
  nombre: string;
  celular: string;
  correo: string | null;
  cc: string | null;
  saldo: number;
  vip: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  cliente: Cliente;
  es_nuevo: boolean;
}

export interface LoginRequest {
  nombre: string;
  celular: string;
  correo?: string;
  cc?: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly TOKEN_KEY = 'mv_token';
  private readonly CLIENTE_KEY = 'mv_cliente';

  constructor(private http: HttpClient) {}

  login(payload: LoginRequest): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${environment.apiUrl}/auth/login`, payload)
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          localStorage.setItem(this.CLIENTE_KEY, JSON.stringify(res.cliente));
        })
      );
  }

  logout(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.CLIENTE_KEY);
  }

  isAuthenticated(): boolean {
    return !!localStorage.getItem(this.TOKEN_KEY);
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getCliente(): Cliente | null {
    const raw = localStorage.getItem(this.CLIENTE_KEY);
    return raw ? (JSON.parse(raw) as Cliente) : null;
  }
}
