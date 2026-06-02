import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { shareReplay } from 'rxjs/operators';
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
  clientes_activos: number;
  clientes_inactivos: number;
  // Filtrados por mes
  numeros_entregados: number;
  total_aciertos: number;
  efectividad_numerica_pct: number;
  efectividad_personal_pct: number;
  clientes_con_numeros: number;
  directos: number;
  directo_metodo: number;
  tres_directo: number;
  tres_metodo: number;
  clientes_con_aciertos: number;
  numero_mas_frecuente: string | null;
  top_loterias: TopLoteria[];
  // Ganadores por tipo
  ganadores_vip: number;
  ganadores_free: number;
  pct_ganadores_vip: number;
  pct_ganadores_free: number;
  suscripciones_iniciadas: number;
  suscripciones_iniciadas_activas: number;
  nuevos_clientes: number;
  pct_3digitos_diferentes: number;
  total_resultados_mes: number;
  resultados_3dif: number;
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private base = `${environment.apiUrl}/admin/dashboard`;

  private _cache = new Map<string, { ts: number; data$: Observable<DashboardStats> }>();
  private readonly CURRENT_TTL  = 5  * 60 * 1000; // 5 min — mes actual
  private readonly HISTORIC_TTL = 30 * 60 * 1000; // 30 min — meses pasados

  constructor(private http: HttpClient) {}

  getStats(mes?: string) {
    const key = mes ?? 'current';
    const now = Date.now();
    const currentMes = (() => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    })();
    const ttl = (!mes || mes === currentMes) ? this.CURRENT_TTL : this.HISTORIC_TTL;

    const cached = this._cache.get(key);
    if (cached && now - cached.ts < ttl) {
      return cached.data$;
    }

    let params = new HttpParams();
    if (mes) params = params.set('mes', mes);
    const data$ = this.http
      .get<DashboardStats>(this.base, { params })
      .pipe(shareReplay(1));
    this._cache.set(key, { ts: now, data$ });
    return data$;
  }
}
