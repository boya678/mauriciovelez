import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { shareReplay } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface RifaPublic {
  id: string;
  titulo: string;
  descripcion: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  seq_inicio: number;
  seq_fin: number;
  estado: 'activa' | 'finalizada';
  ganador_numero: number | null;
  tiene_imagen: boolean;
  total_boletas: number;
}

export interface Boleta {
  numero: number;
  asignado_en: string;
  es_ganadora: boolean;
}

@Injectable({ providedIn: 'root' })
export class RifasService {
  private base = `${environment.apiUrl}/rifas`;

  private _activaCache$: Observable<RifaPublic | null> | null = null;
  private _activaCacheTime = 0;
  private readonly ACTIVA_TTL_MS = 5 * 60 * 1000; // 5 minutos

  constructor(private http: HttpClient) {}

  getActiva(): Observable<RifaPublic | null> {
    const now = Date.now();
    if (!this._activaCache$ || now - this._activaCacheTime > this.ACTIVA_TTL_MS) {
      this._activaCacheTime = now;
      this._activaCache$ = this.http
        .get<RifaPublic | null>(`${this.base}/activa`)
        .pipe(shareReplay(1));
    }
    return this._activaCache$;
  }

  getMisBoletas(): Observable<Boleta[]> {
    return this.http.get<Boleta[]>(`${this.base}/activa/mis-boletas`);
  }

  getHistorico(): Observable<RifaPublic[]> {
    return this.http.get<RifaPublic[]>(`${this.base}/historico`);
  }

  getMisBoletasHistorico(rifaId: string): Observable<Boleta[]> {
    return this.http.get<Boleta[]>(`${this.base}/historico/${rifaId}/mis-boletas`);
  }

  imagenUrl(rifaId: string): string {
    return `${environment.apiUrl}/rifas/imagen/${rifaId}`;
  }
}
