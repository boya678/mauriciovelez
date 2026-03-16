import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SuscripcionesService, Suscripcion } from '../../core/services/suscripciones.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-suscripciones',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './suscripciones.component.html',
  styleUrl: './suscripciones.component.scss',
})
export class SuscripcionesComponent implements OnInit {
  items = signal<Suscripcion[]>([]);
  total = signal(0);
  page = signal(1);
  size = 20;
  search = '';
  soloActivas = false;
  loading = signal(false);
  renovandoId: string | null = null;
  runningCheck = signal(false);

  constructor(public auth: AuthService, private svc: SuscripcionesService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list(this.page(), this.size, this.search, this.soloActivas).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.loading.set(false);
    });
  }

  filtrar() { this.page.set(1); this.load(); }

  get totalPages() { return Math.ceil(this.total() / this.size) || 1; }
  prev() { if (this.page() > 1) { this.page.update(p => p - 1); this.load(); } }
  next() { if (this.page() < this.totalPages) { this.page.update(p => p + 1); this.load(); } }

  renovar(s: Suscripcion) {
    this.renovandoId = s.id;
    this.svc.renovar(s.id).subscribe({
      next: updated => {
        this.items.update(list => list.map(x => x.id === updated.id ? updated : x));
        this.renovandoId = null;
      },
      error: () => { this.renovandoId = null; },
    });
  }

  estadoBadge(s: Suscripcion): 'activa' | 'vencida' {
    return s.activa && new Date(s.fin) >= new Date() ? 'activa' : 'vencida';
  }

  diasRestantes(s: Suscripcion): number {
    const diff = new Date(s.fin).getTime() - Date.now();
    return Math.max(0, Math.ceil(diff / 86400000));
  }

  runVipCheck() {
    this.runningCheck.set(true);
    this.svc.runVipCheck().subscribe({
      next: () => { this.runningCheck.set(false); this.load(); },
      error: () => { this.runningCheck.set(false); },
    });
  }

  downloadExcel() {
    this.svc.export(this.search, this.soloActivas).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'suscripciones.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    });
  }
}
