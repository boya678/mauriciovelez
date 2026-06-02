import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  RifasAdminService,
  RifaItem,
  TipoClienteItem,
  BoletaAdminItem,
} from '../../core/services/rifas-admin.service';

@Component({
  selector: 'app-rifas',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './rifas.component.html',
  styleUrl: './rifas.component.scss',
})
export class RifasComponent implements OnInit {
  rifas = signal<RifaItem[]>([]);
  tiposCliente = signal<TipoClienteItem[]>([]);
  loading = signal(false);
  errorMsg = signal('');
  saving = signal(false);

  // Modal creación/edición
  showModal = signal(false);
  editId: string | null = null;

  // Campos del formulario
  fTitulo = '';
  fDescripcion = '';
  fFechaInicio = '';
  fFechaFin = '';
  fSeqInicio = 0;
  fSeqFin = 9999;
  fBoletasPorRenovacion = 1;
  fSoloVip = false;
  fTiposCliente: number[] = [];
  fFile: File | null = null;
  fPreview: string | null = null;

  // Panel boletas
  rifaSeleccionada: RifaItem | null = null;
  boletas = signal<BoletaAdminItem[]>([]);
  boletasTotal = 0;
  boletasPage = 1;
  loadingBoletas = signal(false);

  // Modal ganador
  showGanadorModal = signal(false);
  rifaGanador: RifaItem | null = null;
  fNumeroGanador: number | null = null;
  ganadorError = '';

  constructor(private svc: RifasAdminService) {}

  ngOnInit() {
    this.load();
    this.svc.tiposCliente().subscribe({ next: t => this.tiposCliente.set(t) });
  }

  load() {
    this.loading.set(true);
    this.svc.listar().subscribe({
      next: data => { this.rifas.set(data); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  // ── Modal formulario ────────────────────────────────────────────────────

  openNew() {
    this.editId = null;
    this.fTitulo = '';
    this.fDescripcion = '';
    this.fFechaInicio = '';
    this.fFechaFin = '';
    this.fSeqInicio = 0;
    this.fSeqFin = 9999;
    this.fBoletasPorRenovacion = 1;
    this.fSoloVip = false;
    this.fTiposCliente = [];
    this.fFile = null;
    this.fPreview = null;
    this.errorMsg.set('');
    this.showModal.set(true);
  }

  openEdit(rifa: RifaItem) {
    this.editId = rifa.id;
    this.fTitulo = rifa.titulo;
    this.fDescripcion = rifa.descripcion ?? '';
    this.fFechaInicio = rifa.fecha_inicio;
    this.fFechaFin = rifa.fecha_fin;
    this.fSeqInicio = rifa.seq_inicio;
    this.fSeqFin = rifa.seq_fin;
    this.fBoletasPorRenovacion = rifa.boletas_por_renovacion;
    this.fSoloVip = rifa.solo_vip;
    this.fTiposCliente = [...rifa.tipos_cliente];
    this.fFile = null;
    this.fPreview = rifa.tiene_imagen ? this.svc.imagenUrl(rifa.id) : null;
    this.errorMsg.set('');
    this.showModal.set(true);
  }

  closeModal() { this.showModal.set(false); }

  onFileChange(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.fFile = file;
    const reader = new FileReader();
    reader.onload = () => { this.fPreview = reader.result as string; };
    reader.readAsDataURL(file);
  }

  toggleTipo(id: number) {
    const idx = this.fTiposCliente.indexOf(id);
    if (idx >= 0) {
      this.fTiposCliente.splice(idx, 1);
    } else {
      this.fTiposCliente.push(id);
    }
  }

  isTipoSelected(id: number): boolean {
    return this.fTiposCliente.includes(id);
  }

  save() {
    if (!this.fTitulo.trim() || !this.fFechaInicio || !this.fFechaFin) {
      this.errorMsg.set('Título, fecha inicio y fecha fin son requeridos.');
      return;
    }
    this.saving.set(true);
    this.errorMsg.set('');

    const fd = new FormData();
    fd.append('titulo', this.fTitulo.trim());
    fd.append('descripcion', this.fDescripcion.trim());
    fd.append('fecha_inicio', this.fFechaInicio);
    fd.append('fecha_fin', this.fFechaFin);
    fd.append('seq_inicio', String(this.fSeqInicio));
    fd.append('seq_fin', String(this.fSeqFin));
    fd.append('boletas_por_renovacion', String(this.fBoletasPorRenovacion));
    fd.append('solo_vip', this.fSoloVip ? 'true' : 'false');
    fd.append('tipos_cliente', JSON.stringify(this.fTiposCliente));
    if (this.fFile) fd.append('imagen', this.fFile);

    const req$ = this.editId
      ? this.svc.editar(this.editId, fd)
      : this.svc.crear(fd);

    req$.subscribe({
      next: () => { this.saving.set(false); this.showModal.set(false); this.load(); },
      error: (err) => {
        this.saving.set(false);
        this.errorMsg.set(err?.error?.detail ?? 'Error al guardar la rifa.');
      },
    });
  }

  // ── Panel boletas ──────────────────────────────────────────────────────

  verBoletas(rifa: RifaItem) {
    if (this.rifaSeleccionada?.id === rifa.id) {
      this.rifaSeleccionada = null;
      return;
    }
    this.rifaSeleccionada = rifa;
    this.boletasPage = 1;
    this.cargarBoletas();
  }

  cargarBoletas() {
    if (!this.rifaSeleccionada) return;
    this.loadingBoletas.set(true);
    this.svc.boletas(this.rifaSeleccionada.id, this.boletasPage).subscribe({
      next: res => {
        this.boletas.set(res.items);
        this.boletasTotal = res.total;
        this.loadingBoletas.set(false);
      },
      error: () => this.loadingBoletas.set(false),
    });
  }

  prevPage() { if (this.boletasPage > 1) { this.boletasPage--; this.cargarBoletas(); } }
  nextPage() {
    if (this.boletasPage * 50 < this.boletasTotal) {
      this.boletasPage++;
      this.cargarBoletas();
    }
  }

  // ── Ganador ────────────────────────────────────────────────────────────

  openGanador(rifa: RifaItem) {
    this.rifaGanador = rifa;
    this.fNumeroGanador = null;
    this.ganadorError = '';
    this.showGanadorModal.set(true);
  }

  closeGanadorModal() { this.showGanadorModal.set(false); }

  guardarGanador() {
    if (this.fNumeroGanador === null || !this.rifaGanador) return;
    this.svc.registrarGanador(this.rifaGanador.id, this.fNumeroGanador).subscribe({
      next: () => { this.showGanadorModal.set(false); this.load(); },
      error: (err) => { this.ganadorError = err?.error?.detail ?? 'Error al registrar ganador.'; },
    });
  }

  finalizar(rifa: RifaItem) {
    if (!confirm(`¿Finalizar la rifa "${rifa.titulo}" sin registrar ganador?`)) return;
    this.svc.finalizar(rifa.id).subscribe({ next: () => this.load() });
  }

  // ── Utilidades ─────────────────────────────────────────────────────────

  imagenUrl(id: string): string { return this.svc.imagenUrl(id); }

  formatNum(n: number, seqFin: number): string {
    const digits = String(seqFin).length;
    return String(n).padStart(digits, '0');
  }

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.boletasTotal / 50));
  }
}
