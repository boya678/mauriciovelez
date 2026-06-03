import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TransaccionesService, Transaccion } from '../../core/services/transacciones.service';

@Component({
  selector: 'app-transacciones',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './transacciones.component.html',
  styleUrl: './transacciones.component.scss',
})
export class TransaccionesComponent implements OnInit {
  items = signal<Transaccion[]>([]);
  loading = signal(false);
  error = signal('');
  fecha = '';
  lightboxSrc = signal<string | null>(null);
  page = signal(1);
  totalPages = signal(1);
  total = signal(0);

  constructor(private svc: TransaccionesService) {}

  ngOnInit() {
    this.fecha = new Date().toISOString().slice(0, 10);
    this.load();
  }

  load() {
    this.loading.set(true);
    this.error.set('');
    this.svc.getTransacciones(this.fecha, this.page()).subscribe({
      next: (data) => {
        this.items.set(data.items);
        this.total.set(data.total);
        this.totalPages.set(data.pages);
        this.loading.set(false);
      },
      error: () => { this.error.set('Error al cargar transacciones'); this.loading.set(false); },
    });
  }

  onFechaChange() {
    this.page.set(1);
    this.load();
  }

  prevPage() {
    if (this.page() > 1) { this.page.update(p => p - 1); this.load(); }
  }

  nextPage() {
    if (this.page() < this.totalPages()) { this.page.update(p => p + 1); this.load(); }
  }

  imgSrc(t: Transaccion): string {
    if (!t.media_content || !t.media_mime_type) return '';
    return `data:${t.media_mime_type};base64,${t.media_content}`;
  }

  openLightbox(src: string) {
    this.lightboxSrc.set(src);
  }

  closeLightbox() {
    this.lightboxSrc.set(null);
  }

}
