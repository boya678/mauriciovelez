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

  // Acciones
  actionLoading = signal<string | null>(null); // id de la transaccion en proceso

  // Modal eliminar
  modalEliminar = signal<Transaccion | null>(null);
  modalEliminarError = signal('');

  // Modal renovar
  modalRenovar = signal<Transaccion | null>(null);
  modalRenovarError = signal('');
  modalRenovarExito = signal('');

  // Modal mensaje
  modalMensaje = signal<Transaccion | null>(null);
  textoMensaje = '';
  modalLoading = signal(false);
  modalError = signal('');

  constructor(private svc: TransaccionesService) {}

  ngOnInit() {
    this.fecha = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota' }).format(new Date());
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

  // ── Acciones ──────────────────────────────────────────────────────────────

  onEliminar(t: Transaccion) {
    this.modalEliminarError.set('');
    this.modalEliminar.set(t);
  }

  closeModalEliminar() {
    this.modalEliminar.set(null);
    this.modalEliminarError.set('');
  }

  confirmarEliminar() {
    const t = this.modalEliminar();
    if (!t) return;
    this.actionLoading.set(t.id);
    this.svc.eliminar(t.id).subscribe({
      next: () => {
        this.actionLoading.set(null);
        this.items.update(list => list.filter(i => i.id !== t.id));
        this.total.update(n => n - 1);
        this.closeModalEliminar();
      },
      error: () => {
        this.actionLoading.set(null);
        this.modalEliminarError.set('Error al eliminar la transacción');
      },
    });
  }

  onRenovar(t: Transaccion) {
    this.modalRenovarError.set('');
    this.modalRenovarExito.set('');
    this.modalRenovar.set(t);
  }

  closeModalRenovar() {
    this.modalRenovar.set(null);
    this.modalRenovarError.set('');
    this.modalRenovarExito.set('');
  }

  confirmarRenovar() {
    const t = this.modalRenovar();
    if (!t) return;
    this.actionLoading.set(t.id);
    this.modalRenovarError.set('');
    this.svc.renovar(t.id).subscribe({
      next: (res) => {
        this.actionLoading.set(null);
        this.items.update(list => list.filter(i => i.id !== t.id));
        this.total.update(n => n - 1);
        const fecha = new Intl.DateTimeFormat('es-CO', {
          timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric'
        }).format(new Date(res.nueva_fin));
        this.modalRenovarExito.set(`Suscripción renovada para ${res.cliente}. Vence: ${fecha}`);
      },
      error: (err) => {
        this.actionLoading.set(null);
        this.modalRenovarError.set(err?.error?.detail || 'Error al renovar la suscripción');
      },
    });
  }

  openModalMensaje(t: Transaccion) {
    this.modalMensaje.set(t);
    this.textoMensaje = '';
    this.modalError.set('');
  }

  closeModalMensaje() {
    this.modalMensaje.set(null);
    this.textoMensaje = '';
    this.modalError.set('');
  }

  onEnviarMensaje() {
    const t = this.modalMensaje();
    if (!t) return;
    if (!this.textoMensaje.trim()) { this.modalError.set('El mensaje no puede estar vacío'); return; }
    this.modalLoading.set(true);
    this.modalError.set('');
    this.svc.enviarMensaje(t.id, this.textoMensaje.trim()).subscribe({
      next: () => {
        this.modalLoading.set(false);
        this.closeModalMensaje();
      },
      error: (err) => {
        this.modalLoading.set(false);
        this.modalError.set(err?.error?.detail || 'Error al enviar el mensaje');
      },
    });
  }
}

