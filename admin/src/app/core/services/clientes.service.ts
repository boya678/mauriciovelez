import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface Cliente {
  id: string;
  nombre: string;
  celular: string;
  correo: string | null;
  cc: string | null;
  saldo: number;
  vip: boolean;
  codigo_vip: string | null;
}

export interface PaginatedClientes {
  total: number;
  page: number;
  size: number;
  items: Cliente[];
}

@Injectable({ providedIn: 'root' })
export class ClientesService {
  private base = `${environment.apiUrl}/admin/clientes`;

  constructor(private http: HttpClient) {}

  list(page = 1, size = 20, q = '') {
    let params = new HttpParams().set('page', page).set('size', size);
    if (q) params = params.set('q', q);
    return this.http.get<PaginatedClientes>(this.base, { params });
  }

  create(data: Partial<Cliente>) {
    return this.http.post<Cliente>(this.base, data);
  }

  update(id: string, data: Partial<Cliente>) {
    return this.http.put<Cliente>(`${this.base}/${id}`, data);
  }

  delete(id: string) {
    return this.http.delete(`${this.base}/${id}`);
  }

  exportAll(q = '') {
    let params = new HttpParams();
    if (q) params = params.set('q', q);
    return this.http.get(`${this.base}/export`, { params, responseType: 'blob' });
  }
}
