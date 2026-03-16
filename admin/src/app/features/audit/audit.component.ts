import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuditService, AuditEntry } from '../../core/services/audit.service';
import { AuthService } from '../../core/services/auth.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-audit',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './audit.component.html',
  styleUrl: './audit.component.scss',
})
export class AuditComponent implements OnInit {
  items = signal<AuditEntry[]>([]);
  total = signal(0);
  page = signal(1);
  size = 50;
  entityFilter = '';
  loading = signal(false);

  entities = ['', 'clientes', 'platform_users'];

  constructor(private svc: AuditService, auth: AuthService, router: Router) {
    if (!auth.isAdmin()) router.navigate(['/admin/clientes']);
  }

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list(this.page(), this.size, this.entityFilter).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.loading.set(false);
    });
  }

  onFilter() { this.page.set(1); this.load(); }

  get totalPages() { return Math.ceil(this.total() / this.size); }
  prev() { if (this.page() > 1) { this.page.update(p => p - 1); this.load(); } }
  next() { if (this.page() < this.totalPages) { this.page.update(p => p + 1); this.load(); } }

  detailStr(e: AuditEntry) {
    if (!e.detail) return '—';
    return JSON.stringify(e.detail);
  }

  actionClass(action: string) {
    const map: Record<string, string> = { CREATE: 'success', UPDATE: 'warning', DELETE: 'danger', LOGIN: 'accent', RENOVAR: 'info' };
    return map[action] ?? '';
  }
}
