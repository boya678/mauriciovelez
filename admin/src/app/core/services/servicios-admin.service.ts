import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface NumeroRelampagoConfig {
  activo: boolean;
  valor: number;
  numero: string;
}

export interface ConferenciaConfig {
  activo: boolean;
  valor: number;
  fecha_aviso: string;
  link_youtube: string;
}

export interface ConferenciaVipConfig {
  activo: boolean;
  valor: number;
  fecha_aviso: string;
  link_youtube: string;
}

@Injectable({ providedIn: 'root' })
export class ServiciosAdminService {
  private base = `${environment.apiUrl}/admin/servicios`;

  constructor(private http: HttpClient) {}

  getNumeroRelampago() {
    return this.http.get<NumeroRelampagoConfig>(`${this.base}/numero-relampago`);
  }

  updateNumeroRelampago(payload: NumeroRelampagoConfig) {
    return this.http.put<NumeroRelampagoConfig>(`${this.base}/numero-relampago`, payload);
  }

  getConferencia() {
    return this.http.get<ConferenciaConfig>(`${this.base}/conferencia`);
  }

  updateConferencia(payload: ConferenciaConfig) {
    return this.http.put<ConferenciaConfig>(`${this.base}/conferencia`, payload);
  }

  getConferenciaVip() {
    return this.http.get<ConferenciaVipConfig>(`${this.base}/conferencia-vip`);
  }

  updateConferenciaVip(payload: ConferenciaVipConfig) {
    return this.http.put<ConferenciaVipConfig>(`${this.base}/conferencia-vip`, payload);
  }
}
