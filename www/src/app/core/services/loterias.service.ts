import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface LoteriaResultado {
  fecha: string;
  loteria: string;
  slug: string;
  resultado: string;
  total_aciertos: number;
}

export interface GanadoresSemana {
  total_ganadores: number;
  dias: number;
}

@Injectable({ providedIn: 'root' })
export class LoteriasService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getResultados(fecha: string): Observable<LoteriaResultado[]> {
    return this.http.get<LoteriaResultado[]>(
      `${this.api}/public/loterias/resultados`,
      { params: { fecha } }
    );
  }

  getGanadoresSemana(): Observable<GanadoresSemana> {
    return this.http.get<GanadoresSemana>(
      `${this.api}/public/loterias/stats/semana`
    );
  }
}
