import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

export interface AuditEntry {
  id: number;
  usuario: string;
  action: string;
  entity: string;
  entity_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface PaginatedAudit {
  total: number;
  page: number;
  size: number;
  items: AuditEntry[];
}

@Injectable({ providedIn: 'root' })
export class AuditService {
  private base = `${environment.apiUrl}/admin/audit`;
  constructor(private http: HttpClient) {}

  list(page = 1, size = 50, entity = '') {
    let params = new HttpParams().set('page', page).set('size', size);
    if (entity) params = params.set('entity', entity);
    return this.http.get<PaginatedAudit>(this.base, { params });
  }
}
