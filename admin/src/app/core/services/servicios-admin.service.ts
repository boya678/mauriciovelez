import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface NumeroRelampagoConfig {
  activo: boolean;
  valor: number;
  numero: string;
}

export interface VipConfig {
  activo: boolean;
  valor: number;
}

export interface TablaNumerologicaConfig {
  activo: boolean;
  valor: number;
  tiene_foto: boolean;
}

export interface RelampagoPersonalizadoConfig {
  activo: boolean;
  valor: number;
  vigencia_dias: number;
  rifa_activo: boolean;
  rifa_descripcion: string;
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

  getVip() {
    return this.http.get<VipConfig>(`${this.base}/vip`);
  }

  updateVip(payload: VipConfig) {
    return this.http.put<VipConfig>(`${this.base}/vip`, payload);
  }

  getTablaNumerologica() {
    return this.http.get<TablaNumerologicaConfig>(`${this.base}/tabla-numerologica`);
  }

  updateTablaNumerologica(payload: { activo: boolean; valor: number }) {
    return this.http.put<TablaNumerologicaConfig>(`${this.base}/tabla-numerologica`, payload);
  }

  subirFotoTablaNumerologica(foto: File) {
    const form = new FormData();
    form.append('foto', foto);
    return this.http.post<TablaNumerologicaConfig>(`${this.base}/tabla-numerologica/foto`, form);
  }

  exportarTablaNumerologica(fechaInicio?: string, fechaFin?: string) {
    let params = new HttpParams();
    if (fechaInicio) params = params.set('fecha_inicio', fechaInicio);
    if (fechaFin) params = params.set('fecha_fin', fechaFin);
    return this.http.get(`${this.base}/tabla-numerologica/exportar`, { params, responseType: 'blob' });
  }

  getRelampagoPersonalizado() {
    return this.http.get<RelampagoPersonalizadoConfig>(`${this.base}/relampago-personalizado`);
  }

  updateRelampagoPersonalizado(payload: RelampagoPersonalizadoConfig) {
    return this.http.put<RelampagoPersonalizadoConfig>(`${this.base}/relampago-personalizado`, payload);
  }

  exportarNumerosRifa(fechaInicio?: string, fechaFin?: string) {
    let params = new HttpParams();
    if (fechaInicio) params = params.set('fecha_inicio', fechaInicio);
    if (fechaFin) params = params.set('fecha_fin', fechaFin);
    return this.http.get(`${this.base}/relampago-personalizado/rifa/exportar`, { params, responseType: 'blob' });
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
