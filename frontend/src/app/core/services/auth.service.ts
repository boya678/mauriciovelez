import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
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
  enabled: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  cliente: Cliente;
  es_nuevo: boolean;
  disabled_msg: string | null;
}

export interface LoginRequest {
  nombre: string;
  celular: string;
  otp_code: string;
  correo?: string;
  cc?: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly TOKEN_KEY = 'mv_token';
  private readonly CLIENTE_KEY = 'mv_cliente';
  private readonly DISABLED_MSG_KEY = 'mv_disabled_msg';

  constructor(private http: HttpClient) {}

  sendOtp(celular: string): Observable<{ ok: boolean; expira_en: number }> {
    return this.http.post<{ ok: boolean; expira_en: number }>(
      `${environment.apiUrl}/auth/send-otp`,
      { celular }
    );
  }

  login(payload: LoginRequest): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${environment.apiUrl}/auth/login`, payload)
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          localStorage.setItem(this.CLIENTE_KEY, JSON.stringify(res.cliente));
          if (res.disabled_msg) {
            localStorage.setItem(this.DISABLED_MSG_KEY, res.disabled_msg);
          } else {
            localStorage.removeItem(this.DISABLED_MSG_KEY);
          }
        })
      );
  }

  verifyVip(clienteId: string, codigo: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${environment.apiUrl}/auth/verify-vip`, {
      cliente_id: clienteId,
      codigo,
    });
  }

  getMiSuscripcion(): Observable<{ vip: boolean; fin: string | null }> {
    return this.http.get<{ vip: boolean; fin: string | null }>(
      `${environment.apiUrl}/auth/mi-suscripcion`,
      { headers: this.authHeaders() }
    );
  }

  updateMisDatos(data: { nombre: string; celular: string; correo?: string | null; cc?: string | null }): Observable<LoginResponse> {
    return this.http
      .put<LoginResponse>(`${environment.apiUrl}/auth/mis-datos`, data, { headers: this.authHeaders() })
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          localStorage.setItem(this.CLIENTE_KEY, JSON.stringify(res.cliente));
        })
      );
  }

  private authHeaders(): HttpHeaders {
    const token = this.getToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }

  logout(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.CLIENTE_KEY);
    localStorage.removeItem(this.DISABLED_MSG_KEY);
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

  getDisabledMsg(): string | null {
    return localStorage.getItem(this.DISABLED_MSG_KEY);
  }

  clearDisabledMsg(): void {
    localStorage.removeItem(this.DISABLED_MSG_KEY);
  }
}
