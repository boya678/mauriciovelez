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
  page = signal(1);
  size = 20;
  search = '';
  filtroVip: 'todos' | 'vip' | 'no_vip' = 'todos';
  loading = signal(false);

  editTarget: Cliente | null = null;
  editForm: Partial<Cliente> = {};
  editError = signal<string | null>(null);
  deleteTarget: Cliente | null = null;

  showCreate = false;
  createForm: Partial<Cliente & { celular: string }> = {};
  createError = signal<string | null>(null);

  private search$ = new Subject<string>();

  constructor(public auth: AuthService, private svc: ClientesService) {}

  ngOnInit() {
    this.load();
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

  onSearch() { this.search$.next(this.search); }

  filtrar() { this.page.set(1); this.load(); }

  get totalPages() { return Math.ceil(this.total() / this.size); }
  prev() { if (this.page() > 1) { this.page.update(p => p - 1); this.load(); } }
  next() { if (this.page() < this.totalPages) { this.page.update(p => p + 1); this.load(); } }

  openEdit(c: Cliente) {
    this.editTarget = c;
    this.editForm = { nombre: c.nombre, celular: c.celular, correo: c.correo ?? '', cc: c.cc ?? '', saldo: c.saldo, vip: c.vip, codigo_vip: c.codigo_vip ?? '', enabled: c.enabled };
    this.editError.set(null);
  }

  openCreate() {
    this.createForm = { nombre: '', celular: '', correo: '', cc: '', saldo: 0, vip: false, codigo_vip: '', enabled: true };
    this.createError.set(null);
    this.showCreate = true;
  }

  saveCreate() {
    this.createError.set(null);
    this.svc.create(this.createForm).subscribe({
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
    this.svc.update(this.editTarget.id, this.editForm).subscribe({
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
