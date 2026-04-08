import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface BannerItem {
  id: string;
  tipo: 'texto' | 'imagen';
  texto: string | null;
  audiencia: 'todos' | 'vip';
  activo: boolean;
  inicio: string;
  fin: string;
  created_at: string;
  tiene_imagen: boolean;
}

export interface PaginatedBanners {
  total: number;
  items: BannerItem[];
}

@Injectable({ providedIn: 'root' })
export class BannersAdminService {
  private base = `${environment.apiUrl}/admin/banners`;

  constructor(private http: HttpClient) {}

  list() {
    return this.http.get<PaginatedBanners>(this.base);
  }

  create(form: FormData) {
    return this.http.post<BannerItem>(this.base, form);
  }

  update(id: string, form: FormData) {
    return this.http.put<BannerItem>(`${this.base}/${id}`, form);
  }

  toggle(id: string) {
    return this.http.patch<BannerItem>(`${this.base}/${id}/toggle`, {});
  }

  delete(id: string) {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
