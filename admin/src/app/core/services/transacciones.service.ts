import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface ClienteInfo {
  registrado: boolean;
  nombre: string | null;
  vip: boolean | null;
  activo: boolean | null;
  tipo_nombre: string | null;
}

export interface Transaccion {
  id: string;
  created_at: string;
  phone: string;
  phone_local: string;
  media_content: string | null;
  media_mime_type: string | null;
  imagen_descripcion: string | null;
  cliente: ClienteInfo;
}

export interface PagedTransacciones {
  total: number;
  page: number;
  pages: number;
  items: Transaccion[];
}

@Injectable({ providedIn: 'root' })
export class TransaccionesService {
  private base = `${environment.apiUrl}/admin/transacciones`;

  constructor(private http: HttpClient) {}

  getTransacciones(fecha?: string, page = 1) {
    let params = new HttpParams().set('page', page.toString());
    if (fecha) params = params.set('fecha', fecha);
    return this.http.get<PagedTransacciones>(this.base, { params });
  }
}
