import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DashboardService, DashboardStats } from '../../core/services/dashboard.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  stats: DashboardStats | null = null;
  loading = signal(true);
  error = signal('');
  selectedMes = '';
  meses: { value: string; label: string }[] = [];

  constructor(private svc: DashboardService) {}

  ngOnInit() {
    this.buildMesesOptions();
    const now = new Date();
    this.selectedMes = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    this.load();
  }

  buildMesesOptions() {
    const now = new Date();
    for (let i = 0; i < 24; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      const label = d.toLocaleString('es-CO', { month: 'long', year: 'numeric' });
      this.meses.push({ value, label: label.charAt(0).toUpperCase() + label.slice(1) });
    }
  }

  onMesChange() {
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.svc.getStats(this.selectedMes).subscribe({
      next: (data) => { this.stats = data; this.loading.set(false); },
      error: () => { this.error.set('Error al cargar estadísticas'); this.loading.set(false); },
    });
  }

  barWidth(value: number, max: number): string {
    if (!max) return '0%';
    return Math.round((value / max) * 100) + '%';
  }

  maxAciertos(): number {
    return Math.max(1, ...(this.stats?.top_loterias.map(l => l.aciertos) ?? [1]));
  }
}
