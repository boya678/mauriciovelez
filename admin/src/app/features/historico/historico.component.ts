import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HistoricoService, HistoricoRow } from '../../core/services/historico.service';

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
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

  desde = yesterday();
  hasta = yesterday();

  constructor(private svc: HistoricoService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list(this.desde, this.hasta, this.page(), this.size).subscribe(res => {
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
    this.svc.export(this.desde, this.hasta).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `historico_${this.desde}_${this.hasta}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }
}
