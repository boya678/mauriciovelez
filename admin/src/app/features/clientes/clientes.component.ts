import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { debounceTime, distinctUntilChanged, Subject, switchMap } from 'rxjs';
import { ClientesService, Cliente } from '../../core/services/clientes.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-clientes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './clientes.component.html',
  styleUrl: './clientes.component.scss',
})
export class ClientesComponent implements OnInit {
  items = signal<Cliente[]>([]);
  total = signal(0);
  totalActivos = signal(0);
  totalInactivos = signal(0);
  page = signal(1);
  size = 20;
  search = '';
  filtroVip: 'todos' | 'vip' | 'no_vip' = 'todos';
  loading = signal(false);

  editTarget: Cliente | null = null;
  editForm: Partial<Cliente> = {};
  editError = signal<string | null>(null);
  editBdDia = 0;
  editBdMes = 0;
  editBdAnio = 0;
  deleteTarget: Cliente | null = null;

  showCreate = false;
  createForm: Partial<Cliente & { celular: string }> = {};
  createError = signal<string | null>(null);
  createBdDia = 0;
  createBdMes = 0;
  createBdAnio = 0;

  meses = [
    { v: 1, n: 'Enero' }, { v: 2, n: 'Febrero' }, { v: 3, n: 'Marzo' },
    { v: 4, n: 'Abril' }, { v: 5, n: 'Mayo' }, { v: 6, n: 'Junio' },
    { v: 7, n: 'Julio' }, { v: 8, n: 'Agosto' }, { v: 9, n: 'Septiembre' },
    { v: 10, n: 'Octubre' }, { v: 11, n: 'Noviembre' }, { v: 12, n: 'Diciembre' },
  ];
  anios = Array.from({ length: 91 }, (_, i) => new Date().getFullYear() - 1 - i);

  private search$ = new Subject<string>();

  constructor(public auth: AuthService, private svc: ClientesService) {}

  ngOnInit() {
    this.load();
    this.loadStats();
    this.search$.pipe(
      debounceTime(350),
      distinctUntilChanged(),
      switchMap(q => { this.loading.set(true); return this.svc.list(1, this.size, q, this.filtroVip); }),
    ).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.page.set(1);
      this.loading.set(false);
    });
  }

  load() {
    this.loading.set(true);
    this.svc.list(this.page(), this.size, this.search, this.filtroVip).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.loading.set(false);
    });
  }

  loadStats() {
    this.svc.getStats().subscribe(s => {
      this.totalActivos.set(s.activos);
      this.totalInactivos.set(s.inactivos);
    });
  }

  onSearch() { this.search$.next(this.search); }

  filtrar() { this.page.set(1); this.load(); }

  get totalPages() { return Math.ceil(this.total() / this.size); }
  prev() { if (this.page() > 1) { this.page.update(p => p - 1); this.load(); } }
  next() { if (this.page() < this.totalPages) { this.page.update(p => p + 1); this.load(); } }

  openEdit(c: Cliente) {
    this.editTarget = c;
    this.editForm = { nombre: c.nombre, celular: c.celular, correo: c.correo ?? '', cc: c.cc ?? '', saldo: c.saldo, vip: c.vip, codigo_vip: c.codigo_vip ?? '', enabled: c.enabled };
    if (c.fecha_nacimiento) {
      const [ay, am, ad] = c.fecha_nacimiento.split('-').map(Number);
      this.editBdAnio = ay; this.editBdMes = am; this.editBdDia = ad;
    } else {
      this.editBdDia = 0; this.editBdMes = 0; this.editBdAnio = 0;
    }
    this.editError.set(null);
  }

  openCreate() {
    this.createForm = { nombre: '', celular: '', correo: '', cc: '', saldo: 0, vip: false, codigo_vip: '', enabled: true };
    this.createBdDia = 0; this.createBdMes = 0; this.createBdAnio = 0;
    this.createError.set(null);
    this.showCreate = true;
  }

  diasParaMes(mes: number, anio: number): number[] {
    const max = (mes && anio) ? new Date(anio, mes, 0).getDate() : 31;
    return Array.from({ length: max }, (_, i) => i + 1);
  }

  onCreateMesChange() {
    const max = (this.createBdMes && this.createBdAnio) ? new Date(this.createBdAnio, this.createBdMes, 0).getDate() : 31;
    if (this.createBdDia > max) this.createBdDia = 0;
  }

  onCreateAnioChange() { this.onCreateMesChange(); }

  onEditMesChange() {
    const max = (this.editBdMes && this.editBdAnio) ? new Date(this.editBdAnio, this.editBdMes, 0).getDate() : 31;
    if (this.editBdDia > max) this.editBdDia = 0;
  }

  onEditAnioChange() { this.onEditMesChange(); }

  private composeFecha(dia: number, mes: number, anio: number): string | null {
    if (!dia || !mes || !anio) return null;
    return `${anio}-${mes.toString().padStart(2, '0')}-${dia.toString().padStart(2, '0')}`;
  }

  saveCreate() {
    this.createError.set(null);
    if (this.createForm.vip && !this.createForm.codigo_vip?.trim()) {
      this.createError.set('El código VIP es obligatorio cuando el cliente es VIP');
      return;
    }
    const payload = { ...this.createForm, fecha_nacimiento: this.composeFecha(this.createBdDia, this.createBdMes, this.createBdAnio) };
    this.svc.create(payload).subscribe({
      next: () => { this.showCreate = false; this.load(); },
      error: (err) => {
        const msg = err?.error?.detail;
        this.createError.set(msg ?? 'Error al crear el cliente');
      },
    });
  }

  saveEdit() {
    if (!this.editTarget) return;
    this.editError.set(null);
    // Si el cliente ya era VIP, no permitir quitarle el VIP desde el admin
    if (this.editTarget.vip) {
      this.editForm.vip = true;
    }
    if (this.editForm.vip && !this.editForm.codigo_vip?.trim()) {
      this.editError.set('El código VIP es obligatorio cuando el cliente es VIP');
      return;
    }
    const payload = { ...this.editForm, fecha_nacimiento: this.composeFecha(this.editBdDia, this.editBdMes, this.editBdAnio) };
    this.svc.update(this.editTarget.id, payload).subscribe({
      next: () => { this.editTarget = null; this.load(); },
      error: (err) => {
        const msg = err?.error?.detail;
        this.editError.set(msg ?? 'Error al guardar los cambios');
      },
    });
  }

  openDelete(c: Cliente) { this.deleteTarget = c; }

  confirmDelete() {
    if (!this.deleteTarget) return;
    this.svc.delete(this.deleteTarget.id).subscribe(() => {
      this.deleteTarget = null;
      this.load();
    });
  }

  downloadExcel() {
    this.svc.exportAll(this.search).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'clientes.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  generateCode() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    this.editForm.codigo_vip = Array.from({ length: 8 }, () =>
      chars[Math.floor(Math.random() * chars.length)]
    ).join('');
  }
}
