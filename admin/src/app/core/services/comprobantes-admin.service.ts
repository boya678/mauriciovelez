import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface ComprobanteVip {
  id: string;
  comprobante_num: string;
  celular: string;
  monto: number;
  descripcion: string;
  message_id: string;
  created_at: string;
}

export interface PagedComprobantes {
  total: number;
  page: number;
  pages: number;
  items: ComprobanteVip[];
}

@Injectable({ providedIn: 'root' })
export class ComprobantesAdminService {
  private base = `${environment.apiUrl}/admin/comprobantes`;

  constructor(private http: HttpClient) {}

  list(filters: { fecha?: string; comprobante_num?: string; page?: number }) {
    let params = new HttpParams();
    if (filters.fecha)           params = params.set('fecha', filters.fecha);
    if (filters.comprobante_num) params = params.set('comprobante_num', filters.comprobante_num);
    if (filters.page)            params = params.set('page', String(filters.page));
    return this.http.get<PagedComprobantes>(this.base, { params });
  }

  exportar(filters: { fecha?: string; comprobante_num?: string }) {
    let params = new HttpParams();
    if (filters.fecha)           params = params.set('fecha', filters.fecha);
    if (filters.comprobante_num) params = params.set('comprobante_num', filters.comprobante_num);
    return this.http.get(`${this.base}/exportar`, { params, responseType: 'blob' });
  }

  delete(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
