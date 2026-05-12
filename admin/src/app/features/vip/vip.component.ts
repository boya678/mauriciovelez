import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { VipService, VipClienteRow } from '../../core/services/vip.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-vip',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './vip.component.html',
  styleUrl: './vip.component.scss',
})
export class VipComponent implements OnInit {
  items = signal<VipClienteRow[]>([]);
  total = signal(0);
  page = signal(1);
  size = 20;
  loading = signal(false);

  soloGanadores = false;
  soloActivos = false;
  soloInactivos = false;

  constructor(public auth: AuthService, private svc: VipService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list(this.page(), this.size, this.soloGanadores, this.soloActivos, this.soloInactivos).subscribe(res => {
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
    this.svc.export(this.soloGanadores, this.soloActivos, this.soloInactivos).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vip_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }
}
