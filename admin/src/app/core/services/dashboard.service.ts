import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface TopLoteria {
  loteria: string;
  aciertos: number;
}

export interface DashboardStats {
  mes: string;
  numeros_entregados: number;
  total_aciertos: number;
  efectividad_pct: number;
  exactos: number;
  tres_orden: number;
  tres_desorden: number;
  clientes_con_aciertos: number;
  numero_mas_frecuente: string | null;
  top_loterias: TopLoteria[];
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private base = `${environment.apiUrl}/admin/dashboard`;

  constructor(private http: HttpClient) {}

  getStats(mes?: string) {
    let params = new HttpParams();
    if (mes) params = params.set('mes', mes);
    return this.http.get<DashboardStats>(this.base, { params });
  }
}
