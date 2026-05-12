import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SuperadminApiService, TokenUsageRow } from '../../../core/services/superadmin-api.service';

interface TenantGroup {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  rows: TokenUsageRow[];
  totalIn: number;
  totalOut: number;
  totalAll: number;
  expanded: boolean;
}

const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

@Component({
  selector: 'app-sa-tokens',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sa-tokens.component.html',
  styleUrl: './sa-tokens.component.scss',
})
export class SaTokensComponent implements OnInit {
  loading = signal(true);
  error = signal('');
  groups = signal<TenantGroup[]>([]);

  filterYear  = new Date().getFullYear();
  filterMonth: number | null = null;

  years = Array.from({ length: 3 }, (_, i) => new Date().getFullYear() - i);
  monthNames = MONTHS;

  constructor(private api: SuperadminApiService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set('');
    this.api.getTokenUsageAll(
      this.filterYear || undefined,
      this.filterMonth ?? undefined,
    ).subscribe({
      next: rows => {
        this.groups.set(this.groupRows(rows));
        this.loading.set(false);
      },
      error: () => {
        this.error.set('No se pudo cargar el uso de tokens.');
        this.loading.set(false);
      },
    });
  }

  private groupRows(rows: TokenUsageRow[]): TenantGroup[] {
    const map = new Map<string, TenantGroup>();
    for (const r of rows) {
      const key = r.tenant_id!;
      if (!map.has(key)) {
        map.set(key, {
          tenant_id: key,
          tenant_name: r.tenant_name ?? key,
          tenant_slug: r.tenant_slug ?? '',
          rows: [],
          totalIn: 0, totalOut: 0, totalAll: 0,
          expanded: false,
        });
      }
      const g = map.get(key)!;
      g.rows.push(r);
      g.totalIn  += r.tokens_in;
      g.totalOut += r.tokens_out;
      g.totalAll += r.tokens_total;
    }
    return [...map.values()].sort((a, b) => b.totalAll - a.totalAll);
  }

  toggle(g: TenantGroup): void {
    g.expanded = !g.expanded;
    this.groups.update(v => [...v]);
  }

  monthLabel(m: number): string {
    return MONTHS[m - 1] ?? String(m);
  }

  calcTotal(field: 'in' | 'out' | 'all'): number {
    return this.groups().reduce((acc, g) => {
      if (field === 'in')  return acc + g.totalIn;
      if (field === 'out') return acc + g.totalOut;
      return acc + g.totalAll;
    }, 0);
  }

  fmt(n: number): string {
    return n.toLocaleString('es-CO');
  }
}
