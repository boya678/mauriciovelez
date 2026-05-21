import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService, ReferidoItem, Aliado } from '../../../core/services/auth.service';

interface MesOption {
  value: string;
  label: string;
}

@Component({
  selector: 'app-referidos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './referidos.component.html',
  styleUrl: './referidos.component.scss',
})
export class ReferidosComponent implements OnInit {
  aliado = signal<Aliado | null>(null);
  referidos = signal<ReferidoItem[]>([]);
  loading = signal(false);
  error = signal('');
  mesSeleccionado = '';
  meses: MesOption[] = [];

  constructor(private auth: AuthService) {}

  ngOnInit(): void {
    this.aliado.set(this.auth.getAliado());
    this.buildMeses();
    this.cargar();
  }

  buildMeses(): void {
    const opts: MesOption[] = [{ value: '', label: 'Todos los meses' }];
    const now = new Date();
    for (let i = 0; i < 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      const label = d.toLocaleDateString('es-CO', { month: 'long', year: 'numeric' });
      opts.push({ value, label });
    }
    this.meses = opts;
  }

  cargar(): void {
    this.loading.set(true);
    this.error.set('');
    this.auth.getMisReferidos(this.mesSeleccionado || undefined).subscribe({
      next: data => { this.referidos.set(data); this.loading.set(false); },
      error: () => { this.error.set('No se pudo cargar la lista de referidos'); this.loading.set(false); },
    });
  }

  filtrarMes(): void { this.cargar(); }

  get saldoFmt(): string {
    const s = this.aliado()?.saldo ?? 0;
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(s);
  }

  fechaFmt(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
  }
}
