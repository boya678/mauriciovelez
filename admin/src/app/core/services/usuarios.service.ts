import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface PlatformUser {
  id: string;
  cc: string;
  nombre: string;
  usuario: string;
  role: string;
  active: boolean;
}

export interface CreateUsuario {
  cc: string;
  nombre: string;
  usuario: string;
  clave: string;
  role: string;
}

export interface UpdateUsuario {
  cc?: string;
  nombre?: string;
  role?: string;
  active?: boolean;
  clave?: string;
}

@Injectable({ providedIn: 'root' })
export class UsuariosService {
  private base = `${environment.apiUrl}/admin/usuarios`;

  constructor(private http: HttpClient) {}

  list()                              { return this.http.get<PlatformUser[]>(this.base); }
  create(data: CreateUsuario)         { return this.http.post<PlatformUser>(this.base, data); }
  update(id: string, data: UpdateUsuario) { return this.http.put<PlatformUser>(`${this.base}/${id}`, data); }
  delete(id: string)                  { return this.http.delete(`${this.base}/${id}`); }
}
