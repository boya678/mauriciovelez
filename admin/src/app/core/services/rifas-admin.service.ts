import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface RifaItem {
  id: string;
  titulo: string;
  descripcion: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  seq_inicio: number;
  seq_fin: number;
  boletas_por_renovacion: number;
  solo_vip: boolean;
  tipos_cliente: number[];
  ganador_numero: number | null;
  estado: 'activa' | 'finalizada';
  tiene_imagen: boolean;
  total_boletas: number;
  created_at: string;
}

export interface TipoClienteItem {
  id: number;
  nombre: string;
}

export interface BoletaAdminItem {
  id: string;
  numero: number;
  nombre: string;
  celular: string;
  asignado_en: string;
}

export interface PaginadoBoletas {
  total: number;
  page: number;
  size: number;
  items: BoletaAdminItem[];
}

@Injectable({ providedIn: 'root' })
export class RifasAdminService {
  private base = `${environment.apiUrl}/admin/rifas`;

  constructor(private http: HttpClient) {}

  listar(): Observable<RifaItem[]> {
    return this.http.get<RifaItem[]>(this.base);
  }

  crear(form: FormData): Observable<RifaItem> {
    return this.http.post<RifaItem>(this.base, form);
  }

  editar(id: string, form: FormData): Observable<RifaItem> {
    return this.http.put<RifaItem>(`${this.base}/${id}`, form);
  }

  registrarGanador(id: string, numero: number): Observable<RifaItem> {
    return this.http.post<RifaItem>(`${this.base}/${id}/ganador`, { numero });
  }

  finalizar(id: string): Observable<RifaItem> {
    return this.http.post<RifaItem>(`${this.base}/${id}/finalizar`, {});
  }

  boletas(id: string, page = 1, size = 50): Observable<PaginadoBoletas> {
    const params = new HttpParams().set('page', page).set('size', size);
    return this.http.get<PaginadoBoletas>(`${this.base}/${id}/boletas`, { params });
  }

  tiposCliente(): Observable<TipoClienteItem[]> {
    return this.http.get<TipoClienteItem[]>(`${this.base}/tipos-cliente`);
  }

  imagenUrl(id: string): string {
    return `${environment.apiUrl}/admin/rifas/${id}/imagen`;
  }
}
