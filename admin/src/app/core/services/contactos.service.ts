import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { tap } from 'rxjs';

export interface Contacto {
  id: string;
  cliente_id: string;
  nombre: string;
  celular: string;
  numero: string;
  loteria: string;
  tipo_acierto: string;
  fecha: string;
  vip: boolean;
}

@Injectable({ providedIn: 'root' })
export class ContactosService {
  private base = `${environment.apiUrl}/admin/contactos`;

  constructor(private http: HttpClient) {}

  list() {
    return this.http.get<Contacto[]>(this.base);
  }

  delete(id: string) {
    return this.http.delete(`${this.base}/${id}`);
  }

  purgeVip() {
    return this.http.delete<{ eliminados: number }>(`${this.base}/purge-vip`);
  }

  export() {
    return this.http.get(`${this.base}/export`, { responseType: 'blob' }).pipe(
      tap(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'contactos.xlsx';
        a.click();
        URL.revokeObjectURL(url);
      })
    );
  }
}
