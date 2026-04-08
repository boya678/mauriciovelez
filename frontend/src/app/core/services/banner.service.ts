import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface BannerPublico {
  id: string;
  tipo: 'texto' | 'imagen';
  texto: string | null;
  imagen_src: string | null;
  audiencia: string;
}

@Injectable({ providedIn: 'root' })
export class BannerService {
  constructor(private http: HttpClient) {}

  getActivo(esVip: boolean): Observable<BannerPublico | null> {
    const params = new HttpParams().set('vip', esVip ? 'true' : 'false');
    return this.http
      .get<BannerPublico | null>(`${environment.apiUrl}/banners/activo`, { params })
      .pipe(catchError(() => of(null)));
  }
}
