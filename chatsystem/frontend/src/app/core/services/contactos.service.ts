import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { AuthService } from './auth.service';
import { environment } from '../../../environments/environment';

export interface Contact {
  phone: string;
  tags: string;
}

@Injectable({ providedIn: 'root' })
export class ContactosService {
  private http = inject(HttpClient);
  private auth = inject(AuthService);

  list(search = '', page = 1, pageSize = 200) {
    let params = new HttpParams().set('page', page).set('page_size', pageSize);
    if (search) params = params.set('search', search);
    return this.http.get<Contact[]>(`${environment.apiUrl}/api/v1/contactos`, { params });
  }

  exportUrl(): string {
    return `${environment.apiUrl}/api/v1/contactos/export`;
  }
}
