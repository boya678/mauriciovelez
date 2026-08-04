import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TransaccionesService, Transaccion, ChequeoResult } from '../../core/services/transacciones.service';

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

  // Modal chequear
  modalChequeo = signal<Transaccion | null>(null);
  chequeoResult = signal<ChequeoResult | null>(null);
  chequeoLoading = signal(false);
  chequeoError = signal('');
  registrarLoading = signal(false);
  registrarExito = signal('');
  comprobanteManual = '';
  descripcionManual = '';
  reprocesarLoading = signal(false);
  reprocesarResult = signal<{ accion: string; detalle: string | null } | null>(null);

  constructor(private svc: TransaccionesService) {}

  ngOnInit() {
    this.fecha = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota' }).format(new Date());
    this.load();
  }

  private getApiErrorMessage(err: any, fallback: string): string {
    const detail = err?.error?.detail;

    if (typeof detail === 'string' && detail.trim()) {
      if (detail.includes('chequear o reprocesar')) {
        return `${detail}. Abre "Chequear" y luego intenta renovar.`;
      }
      if (detail.includes('falta número de comprobante')) {
        return `${detail}. Primero ejecuta "Chequear" o "Reprocesar".`;
      }
      if (detail.includes('falta hash de imagen')) {
        return `${detail}. Reprocesa la imagen para generar el hash.`;
      }
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail.map((d: any) => d?.msg || d?.message || String(d)).join(' | ') || fallback;
    }

    return err?.message || fallback;
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
        this.modalRenovarError.set(this.getApiErrorMessage(err, 'Error al renovar la suscripción'));
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

  // ── Chequear comprobante ───────────────────────────────────────────────────

  onChequear(t: Transaccion) {
    this.modalChequeo.set(t);
    this.chequeoResult.set(null);
    this.chequeoError.set('');
    this.registrarExito.set('');
    this.chequeoLoading.set(true);
    this.svc.chequear(t.id).subscribe({
      next: (res) => { this.chequeoLoading.set(false); this.chequeoResult.set(res); },
      error: (err) => { this.chequeoLoading.set(false); this.chequeoError.set(err?.error?.detail || 'Error al consultar'); },
    });
  }

  closeModalChequeo() {
    this.modalChequeo.set(null);
    this.chequeoResult.set(null);
    this.chequeoError.set('');
    this.registrarExito.set('');
    this.comprobanteManual = '';
    this.descripcionManual = '';
    this.reprocesarResult.set(null);
  }

  onReprocesar() {
    const t = this.modalChequeo();
    if (!t) return;
    this.reprocesarLoading.set(true);
    this.reprocesarResult.set(null);
    this.chequeoError.set('');
    this.registrarExito.set('');
    this.svc.reprocesar(t.id).subscribe({
      next: (res) => {
        this.reprocesarLoading.set(false);
        this.reprocesarResult.set({ accion: res.accion, detalle: res.detalle });
        // Refrescar el chequeo con los nuevos datos
        const prev = this.chequeoResult();
        if (prev) this.chequeoResult.set({
          ...prev,
          analizado_por_ia: true,
          es_comprobante: res.es_comprobante,
          comprobante_num: res.comprobante_num,
          monto_extraido: res.monto_extraido,
          ya_procesado: res.accion === 'ya_procesado' || res.accion === 'renovado' || res.accion === 'cliente_creado',
        });
      },
      error: (err) => {
        this.reprocesarLoading.set(false);
        this.chequeoError.set(err?.error?.detail || 'Error al reprocesar');
      },
    });
  }

  onRegistrarComprobante() {
    const t = this.modalChequeo();
    if (!t) return;
    this.registrarLoading.set(true);
    this.chequeoError.set('');
    this.svc.registrarComprobante(t.id, this.comprobanteManual || undefined, this.descripcionManual).subscribe({
      next: (res) => {
        this.registrarLoading.set(false);
        this.registrarExito.set(`Comprobante '${res.comprobante_num}' registrado para ${res.celular}`);
        // Actualizar el resultado para reflejar que ya está procesado
        const prev = this.chequeoResult();
        if (prev) this.chequeoResult.set({ ...prev, ya_procesado: true, procesado_para_celular: res.celular });
      },
      error: (err) => {
        this.registrarLoading.set(false);
        this.chequeoError.set(err?.error?.detail || 'Error al registrar comprobante');
      },
    });
  }
}

