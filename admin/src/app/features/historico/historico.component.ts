import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HistoricoService, HistoricoRow, AciertoDetalle } from '../../core/services/historico.service';
import { AuthService } from '../../core/services/auth.service';
import { yesterdayCol } from '../../core/utils/col-date';

function yesterday(): string {
  return yesterdayCol();
}

@Component({
  selector: 'app-historico',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './historico.component.html',
  styleUrl: './historico.component.scss',
})
export class HistoricoComponent implements OnInit {
  items = signal<HistoricoRow[]>([]);
  total = signal(0);
  page = signal(1);
  size = 20;
  loading = signal(false);
  exporting = signal(false);

  desde = yesterday();
  hasta = yesterday();
  soloGanadores = false;
  filtroVip: 'todos' | 'vip' | 'no_vip' = 'todos';
  celular = '';

  // Modal aciertos
  showModal = signal(false);
  modalLoading = signal(false);
  modalAciertos = signal<AciertoDetalle[]>([]);
  modalTitle = signal('');

  constructor(public auth: AuthService, private svc: HistoricoService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list(this.desde, this.hasta, this.page(), this.size, this.soloGanadores, this.filtroVip, this.celular).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.loading.set(false);
    });
  }

  filtrar() { this.page.set(1); this.load(); }

  get totalPages() { return Math.ceil(this.total() / this.size) || 1; }
  prev() { if (this.page() > 1) { this.page.update(p => p - 1); this.load(); } }
  next() { if (this.page() < this.totalPages) { this.page.update(p => p + 1); this.load(); } }

  downloadExcel() {
    if (this.exporting()) return;
    this.exporting.set(true);
    this.svc.export(this.desde, this.hasta, this.soloGanadores, this.filtroVip, this.celular).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `historico_${this.desde}_${this.hasta}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        this.exporting.set(false);
      },
      error: () => this.exporting.set(false),
    });
  }

  openAciertos(r: HistoricoRow) {
    this.modalTitle.set(`Aciertos — ${r.nombre} (${r.numero})`);
    this.modalAciertos.set([]);
    this.showModal.set(true);
    this.modalLoading.set(true);
    this.svc.getAciertos(r.id).subscribe({
      next: data => { this.modalAciertos.set(data); this.modalLoading.set(false); },
      error: () => this.modalLoading.set(false),
    });
  }

  closeModal() { this.showModal.set(false); }

  tipoLabel(tipo: string): string {
    const map: Record<string, string> = {
      directo: 'Directo',
      directo_metodo: 'Directo Método',
      tres_directo: 'Tres Directo',
      tres_metodo: 'Tres Método',
    };
    return map[tipo] ?? tipo;
  }
}
