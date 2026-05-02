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
  confirmRenovar: Suscripcion | null = null;
  runningCheck = signal(false);
  toast = signal<{ msg: string; type: 'ok' | 'err' } | null>(null);
  private toastTimer: ReturnType<typeof setTimeout> | null = null;

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
    this.confirmRenovar = s;
  }

  doRenovar() {
    if (!this.confirmRenovar) return;
    const s = this.confirmRenovar;
    this.confirmRenovar = null;
    this.renovandoId = s.id;
    this.svc.renovar(s.id).subscribe({
      next: () => {
        this.renovandoId = null;
        this.showToast('Suscripción renovada correctamente', 'ok');
        this.load();
      },
      error: () => {
        this.renovandoId = null;
        this.showToast('Error al renovar — intenta de nuevo', 'err');
      },
    });
  }

  private showToast(msg: string, type: 'ok' | 'err') {
    if (this.toastTimer) clearTimeout(this.toastTimer);
    this.toast.set({ msg, type });
    this.toastTimer = setTimeout(() => this.toast.set(null), 3500);
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
