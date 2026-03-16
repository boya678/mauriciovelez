import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface Suscripcion {
  id: string;
  cliente_id: string;
  nombre: string;
  celular: string;
  inicio: string;
  fin: string;
  activa: boolean;
  created_at: string;
}

export interface PaginatedSuscripciones {
  total: number;
  page: number;
  size: number;
  items: Suscripcion[];
}

@Injectable({ providedIn: 'root' })
export class SuscripcionesService {
  private base = `${environment.apiUrl}/admin/suscripciones`;

  constructor(private http: HttpClient) {}

  list(page = 1, size = 20, q = '', soloActivas = false) {
    let params = new HttpParams()
      .set('page', page)
      .set('size', size)
      .set('solo_activas', soloActivas);
    if (q) params = params.set('q', q);
    return this.http.get<PaginatedSuscripciones>(this.base, { params });
  }

  renovar(id: string) {
    return this.http.post<Suscripcion>(`${this.base}/${id}/renovar`, {});
  }

  export(q = '', soloActivas = false) {
    let params = new HttpParams().set('solo_activas', soloActivas);
    if (q) params = params.set('q', q);
    return this.http.get(`${this.base}/export`, { params, responseType: 'blob' });
  }

  runVipCheck() {
    return this.http.post<{ ok: boolean; mensaje: string }>(`${this.base}/run-vip-check`, {});
  }
}
