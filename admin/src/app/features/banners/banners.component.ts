import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BannersAdminService, BannerItem } from '../../core/services/banners-admin.service';

@Component({
  selector: 'app-banners',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './banners.component.html',
  styleUrl: './banners.component.scss',
})
export class BannersComponent implements OnInit {
  items = signal<BannerItem[]>([]);
  loading = signal(false);
  errorMsg = signal('');

  // Modal
  showModal = signal(false);
  saving = signal(false);
  editId: string | null = null;

  // Form fields
  fTipo: 'texto' | 'imagen' = 'texto';
  fTexto = '';
  fAudiencia: 'todos' | 'vip' = 'todos';
  fInicio = '';
  fFin = '';
  fFile: File | null = null;
  fPreview: string | null = null;
  fFileError = '';

  constructor(private svc: BannersAdminService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.svc.list().subscribe({
      next: res => { this.items.set(res.items); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  openNew() {
    this.editId = null;
    this.fTipo = 'texto';
    this.fTexto = '';
    this.fAudiencia = 'todos';
    this.fInicio = '';
    this.fFin = '';
    this.fFile = null;
    this.fPreview = null;
    this.fFileError = '';
    this.errorMsg.set('');
    this.showModal.set(true);
  }

  openEdit(b: BannerItem) {
    this.editId = b.id;
    this.fTipo = b.tipo;
    this.fTexto = b.texto ?? '';
    this.fAudiencia = b.audiencia;
    this.fInicio = b.inicio.slice(0, 16);
    this.fFin = b.fin.slice(0, 16);
    this.fFile = null;
    this.fPreview = null;
    this.fFileError = '';
    this.errorMsg.set('');
    this.showModal.set(true);
  }

  closeModal() { this.showModal.set(false); }

  onFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    this.fFileError = '';
    this.fFile = null;
    this.fPreview = null;
    if (!file) return;

    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowed.includes(file.type)) {
      this.fFileError = 'Formato no permitido. Use JPEG, PNG o WebP.';
      input.value = '';
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      this.fFileError = `El archivo excede 2 MB (${Math.round(file.size / 1024)} KB).`;
      input.value = '';
      return;
    }

    // Verificar dimensiones antes de enviar
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const { width: w, height: h } = img;
      if (w < 800) {
        this.fFileError = `El ancho mínimo es 800 px. Recibida: ${w} px.`;
        URL.revokeObjectURL(url); input.value = ''; return;
      }
      const ratio = w / h;
      if (ratio < 2 || ratio > 8) {
        this.fFileError = `Proporción inválida (${w}×${h}, ratio ${ratio.toFixed(2)}:1). Debe ser entre 2:1 y 8:1. Ej: 1200×300, 1920×400.`;
        URL.revokeObjectURL(url); input.value = ''; return;
      }
      this.fFile = file;
      this.fPreview = url;
    };
    img.onerror = () => { URL.revokeObjectURL(url); this.fFileError = 'No se pudo leer la imagen.'; };
    img.src = url;
  }

  save() {
    this.errorMsg.set('');
    if (!this.fInicio || !this.fFin) { this.errorMsg.set('Las fechas de inicio y fin son requeridas.'); return; }
    if (new Date(this.fFin) <= new Date(this.fInicio)) { this.errorMsg.set('La fecha de fin debe ser posterior al inicio.'); return; }
    if (this.fTipo === 'texto' && !this.fTexto.trim()) { this.errorMsg.set('El texto del banner no puede estar vacío.'); return; }
    if (this.fTipo === 'imagen' && !this.editId && !this.fFile) { this.errorMsg.set('Debe seleccionar una imagen.'); return; }

    const form = new FormData();
    form.append('tipo', this.fTipo);
    form.append('audiencia', this.fAudiencia);
    form.append('inicio', new Date(this.fInicio).toISOString());
    form.append('fin', new Date(this.fFin).toISOString());
    if (this.fTipo === 'texto') form.append('texto', this.fTexto);
    if (this.fTipo === 'imagen' && this.fFile) form.append('imagen', this.fFile);

    this.saving.set(true);
    const req = this.editId
      ? this.svc.update(this.editId, form)
      : this.svc.create(form);

    req.subscribe({
      next: () => { this.saving.set(false); this.showModal.set(false); this.load(); },
      error: (err) => {
        this.saving.set(false);
        const detail = err?.error?.detail;
        this.errorMsg.set(detail ?? 'Error al guardar el banner.');
      },
    });
  }

  toggle(b: BannerItem) {
    this.svc.toggle(b.id).subscribe(() => this.load());
  }

  delete(b: BannerItem) {
    if (!confirm(`¿Eliminar el banner "${b.tipo === 'texto' ? b.texto?.slice(0, 40) : 'imagen'}"?`)) return;
    this.svc.delete(b.id).subscribe(() => this.load());
  }

  isVigente(b: BannerItem): boolean {
    const now = Date.now();
    return b.activo && new Date(b.inicio).getTime() <= now && new Date(b.fin).getTime() >= now;
  }

  audienciaLabel(a: string): string {
    return a === 'vip' ? 'Solo VIP' : 'Todos';
  }
}
