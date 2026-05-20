import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface ResultadoLoteria {
  id: string;
  fecha: string;
  loteria: string;
  slug: string;
  resultado: string;
  serie: string;
  total_aciertos: number;
}

@Injectable({ providedIn: 'root' })
export class LoteriasService {
  private base = `${environment.apiUrl}/admin/loterias`;

  constructor(private http: HttpClient) {}

  getResultados(fecha: string) {
    const params = new HttpParams().set('fecha', fecha);
    return this.http.get<ResultadoLoteria[]>(`${this.base}/resultados`, { params });
  }
}
