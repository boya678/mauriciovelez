import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface TopLoteria {
  loteria: string;
  aciertos: number;
}

export interface DashboardStats {
  mes: string;
  // Totalizados (independientes del mes)
  total_clientes: number;
  clientes_vip: number;
  // Filtrados por mes
  numeros_entregados: number;
  total_aciertos: number;
  efectividad_numerica_pct: number;
  efectividad_personal_pct: number;
  clientes_con_numeros: number;
  exactos: number;
  directo_devuelto: number;
  tres_orden: number;
  tres_desorden: number;
  clientes_con_aciertos: number;
  numero_mas_frecuente: string | null;
  top_loterias: TopLoteria[];
  // Ganadores por tipo
  ganadores_vip: number;
  ganadores_free: number;
  pct_ganadores_vip: number;
  pct_ganadores_free: number;
  suscripciones_iniciadas: number;
  nuevos_clientes: number;
  pct_3digitos_diferentes: number;
  total_resultados_mes: number;
  resultados_3dif: number;
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
