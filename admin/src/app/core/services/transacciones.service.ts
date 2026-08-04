import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface ClienteInfo {
  registrado: boolean;
  nombre: string | null;
  vip: boolean | null;
  activo: boolean | null;
  tipo_nombre: string | null;
  tipo_cliente: number | null;
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

export interface ChequeoResult {
  analizado_por_ia: boolean;
  es_comprobante: boolean | null;
  comprobante_num: string | null;
  monto_extraido: number | null;
  ya_procesado: boolean;
  procesado_para_celular: string | null;
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

  eliminar(id: string) {
    return this.http.post<{ ok: boolean }>(`${this.base}/${id}/eliminar`, {});
  }

  renovar(id: string) {
    return this.http.post<{ ok: boolean; cliente: string; nueva_fin: string }>(`${this.base}/${id}/renovar`, {});
  }

  enviarMensaje(id: string, texto: string) {
    return this.http.post<{ ok: boolean }>(`${this.base}/${id}/mensaje`, { texto });
  }

  chequear(id: string) {
    return this.http.get<ChequeoResult>(`${this.base}/${id}/chequear`);
  }

  registrarComprobante(id: string, comprobante_num_manual: string | undefined, descripcion: string) {
    return this.http.post<{ ok: boolean; comprobante_num: string; celular: string }>(
      `${this.base}/${id}/registrar-comprobante`,
      { comprobante_num_manual: comprobante_num_manual || undefined, descripcion }
    );
  }

  reprocesar(id: string) {
    return this.http.post<{
      es_comprobante: boolean;
      comprobante_num: string | null;
      monto_extraido: number | null;
      accion: string;
      detalle: string | null;
    }>(`${this.base}/${id}/reprocesar`, {});
  }
}

