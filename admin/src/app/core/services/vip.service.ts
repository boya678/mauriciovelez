import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface VipClienteRow {
  id: string;
  nombre: string;
  celular: string;
  codigo_vip: string | null;
  total_suscripciones: number;
  veces_gano: number;
  suscripcion_activa: boolean;
  cliente_habilitado: boolean;
}

export interface PaginatedVip {
  total: number;
  page: number;
  size: number;
  items: VipClienteRow[];
}

@Injectable({ providedIn: 'root' })
export class VipService {
  private base = `${environment.apiUrl}/admin/vip`;
  constructor(private http: HttpClient) {}

  list(page = 1, size = 20, soloGanadores = false, soloActivos = false, soloInactivos = false) {
    let params = new HttpParams().set('page', page).set('size', size);
    if (soloGanadores) params = params.set('solo_ganadores', 'true');
    if (soloActivos) params = params.set('solo_activos', 'true');
    if (soloInactivos) params = params.set('solo_inactivos', 'true');
    return this.http.get<PaginatedVip>(this.base, { params });
  }

  export(soloGanadores = false, soloActivos = false, soloInactivos = false) {
    let params = new HttpParams();
    if (soloGanadores) params = params.set('solo_ganadores', 'true');
    if (soloActivos) params = params.set('solo_activos', 'true');
    if (soloInactivos) params = params.set('solo_inactivos', 'true');
    return this.http.get(`${this.base}/export`, { params, responseType: 'blob' });
  }
}
