import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface HistoricoRow {
  id: number;
  fecha: string;
  nombre: string;
  celular: string;
  cc: string | null;
  numero: string;
  aciertos: number;
}

export interface AciertoDetalle {
  id: string;
  historic_id: number;
  tipo: string;
  numero: string;
  loteria: string;
  resultado: string;
  fecha: string;
}

export interface PaginatedHistorico {
  total: number;
  page: number;
  size: number;
  items: HistoricoRow[];
}

@Injectable({ providedIn: 'root' })
export class HistoricoService {
  private base = `${environment.apiUrl}/admin/historico`;

  constructor(private http: HttpClient) {}

  list(desde: string, hasta: string, page = 1, size = 20) {
    const params = new HttpParams()
      .set('desde', desde)
      .set('hasta', hasta)
      .set('page', page)
      .set('size', size);
    return this.http.get<PaginatedHistorico>(this.base, { params });
  }

  export(desde: string, hasta: string) {
    const params = new HttpParams().set('desde', desde).set('hasta', hasta);
    return this.http.get(`${this.base}/export`, { params, responseType: 'blob' });
  }

  getAciertos(historicId: number) {
    return this.http.get<AciertoDetalle[]>(
      `${environment.apiUrl}/admin/loterias/aciertos/${historicId}`
    );
  }
}
