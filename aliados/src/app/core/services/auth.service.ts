import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface Aliado {
  id: string;
  nombre: string;
  celular: string;
  saldo: number;
  codigo_vip: string | null;
  tipo_cliente: number;
  fecha_nacimiento: string | null;
  correo: string | null;
  cc: string | null;
  departamento: string | null;
  ciudad: string | null;
  barrio: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  aliado: Aliado;
}

export interface LoginRequest {
  celular: string;
  codigo_vip: string;
}

export interface RegistroOtpRequest {
  celular: string;
  codigo_pais?: string;
}

export interface RegistroRequest {
  nombre: string;
  celular: string;
  codigo_pais?: string;
  correo?: string | null;
  cc?: string | null;
  departamento?: string | null;
  ciudad?: string | null;
  barrio?: string | null;
  otp_code: string;
}

export interface ReferidoItem {
  nombre: string;
  celular: string;
  fecha_registro: string | null;
}

export interface UpdatePerfilRequest {
  nombre: string;
  correo?: string | null;
  cc?: string | null;
  fecha_nacimiento?: string | null;
  departamento?: string | null;
  ciudad?: string | null;
  barrio?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly TOKEN_KEY = 'mv_aliado_token';
  private readonly ALIADO_KEY = 'mv_aliado';

  constructor(private http: HttpClient) {}

  login(payload: LoginRequest): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${environment.apiUrl}/aliados/login`, payload)
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          localStorage.setItem(this.ALIADO_KEY, JSON.stringify(res.aliado));
        })
      );
  }

  sendRegistroOtp(payload: RegistroOtpRequest): Observable<{ ok: boolean; expira_en: number }> {
    return this.http.post<{ ok: boolean; expira_en: number }>(
      `${environment.apiUrl}/aliados/registro/send-otp`,
      payload
    );
  }

  registro(payload: RegistroRequest): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${environment.apiUrl}/aliados/registro`, payload)
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          localStorage.setItem(this.ALIADO_KEY, JSON.stringify(res.aliado));
        })
      );
  }

  getPerfil(): Observable<Aliado> {
    return this.http
      .get<Aliado>(`${environment.apiUrl}/aliados/perfil`, {
        headers: this.authHeaders(),
      })
      .pipe(tap(a => localStorage.setItem(this.ALIADO_KEY, JSON.stringify(a))));
  }

  updatePerfil(data: UpdatePerfilRequest): Observable<Aliado> {
    return this.http
      .put<Aliado>(`${environment.apiUrl}/aliados/perfil`, data, {
        headers: this.authHeaders(),
      })
      .pipe(tap(a => localStorage.setItem(this.ALIADO_KEY, JSON.stringify(a))));
  }

  getMisReferidos(mes?: string): Observable<ReferidoItem[]> {
    let params = new HttpParams();
    if (mes) params = params.set('mes', mes);
    return this.http.get<ReferidoItem[]>(`${environment.apiUrl}/aliados/mis-referidos`, {
      headers: this.authHeaders(),
      params,
    });
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getAliado(): Aliado | null {
    const s = localStorage.getItem(this.ALIADO_KEY);
    return s ? (JSON.parse(s) as Aliado) : null;
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  logout(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.ALIADO_KEY);
  }

  private authHeaders(): HttpHeaders {
    return new HttpHeaders({ Authorization: `Bearer ${this.getToken() ?? ''}` });
  }
}
