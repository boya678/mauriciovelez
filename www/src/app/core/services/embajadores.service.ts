import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

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

export interface RegistroEmbajadorResponse {
  access_token: string;
  token_type: string;
  aliado: {
    codigo_vip: string | null;
  };
}

@Injectable({ providedIn: 'root' })
export class EmbajadoresService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  sendRegistroOtp(payload: RegistroOtpRequest): Observable<{ ok: boolean; expira_en: number }> {
    return this.http.post<{ ok: boolean; expira_en: number }>(
      `${this.api}/aliados/registro/send-otp`,
      payload
    );
  }

  registro(payload: RegistroRequest): Observable<RegistroEmbajadorResponse> {
    return this.http.post<RegistroEmbajadorResponse>(`${this.api}/aliados/registro`, payload);
  }
}
