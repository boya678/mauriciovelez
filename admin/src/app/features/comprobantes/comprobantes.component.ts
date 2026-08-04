import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ComprobantesAdminService, ComprobanteVip, PagedComprobantes } from '../../core/services/comprobantes-admin.service';

@Component({
  selector: 'app-comprobantes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './comprobantes.component.html',
  styleUrl: './comprobantes.component.scss',
})
export class ComprobantesComponent implements OnInit {
  items = signal<ComprobanteVip[]>([]);
  total = signal(0);
  pages = signal(1);
  loading = signal(false);
  error = signal('');

  // Filtros
  filtroFecha = '';
  filtroComprobante = '';
  page = 1;

  // Confirmación de borrado
  confirmDelete = signal<ComprobanteVip | null>(null);
  deleting = signal(false);
  exporting = signal(false);

  constructor(private svc: ComprobantesAdminService) {}

  ngOnInit() {
    this.cargar();
  }

  cargar() {
    this.loading.set(true);
    this.error.set('');
    this.svc.list({
      fecha: this.filtroFecha || undefined,
      comprobante_num: this.filtroComprobante || undefined,
      page: this.page,
    }).subscribe({
      next: res => {
        this.items.set(res.items);
        this.total.set(res.total);
        this.pages.set(res.pages);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Error al cargar comprobantes');
        this.loading.set(false);
      },
    });
  }

  buscar() {
    this.page = 1;
    this.cargar();
  }

  limpiar() {
    this.filtroFecha = '';
    this.filtroComprobante = '';
    this.page = 1;
    this.cargar();
  }

  irPagina(p: number) {
    if (p < 1 || p > this.pages()) return;
    this.page = p;
    this.cargar();
  }

  abrirConfirmDelete(c: ComprobanteVip) {
    this.confirmDelete.set(c);
  }

  cancelarDelete() {
    this.confirmDelete.set(null);
  }

  confirmarDelete() {
    const c = this.confirmDelete();
    if (!c) return;
    this.deleting.set(true);
    this.svc.delete(c.id).subscribe({
      next: () => {
        this.confirmDelete.set(null);
        this.deleting.set(false);
        this.cargar();
      },
      error: () => {
        this.deleting.set(false);
      },
    });
  }

  pagesArray() {
    return Array.from({ length: this.pages() }, (_, i) => i + 1);
  }

  exportar() {
    this.exporting.set(true);
    this.svc.exportar({
      fecha: this.filtroFecha || undefined,
      comprobante_num: this.filtroComprobante || undefined,
    }).subscribe({
      next: (blob: Blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `comprobantes_${this.filtroFecha || 'todos'}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        this.exporting.set(false);
      },
      error: () => this.exporting.set(false),
    });
  }
}
