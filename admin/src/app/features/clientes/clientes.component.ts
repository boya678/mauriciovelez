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
  loading = signal(false);

  editTarget: Cliente | null = null;
  editForm: Partial<Cliente> = {};
  deleteTarget: Cliente | null = null;

  private search$ = new Subject<string>();

  constructor(public auth: AuthService, private svc: ClientesService) {}

  ngOnInit() {
    this.load();
    this.search$.pipe(
      debounceTime(350),
      distinctUntilChanged(),
      switchMap(q => { this.loading.set(true); return this.svc.list(1, this.size, q); }),
    ).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.page.set(1);
      this.loading.set(false);
    });
  }

  load() {
    this.loading.set(true);
    this.svc.list(this.page(), this.size, this.search).subscribe(res => {
      this.items.set(res.items);
      this.total.set(res.total);
      this.loading.set(false);
    });
  }

  onSearch() { this.search$.next(this.search); }

  get totalPages() { return Math.ceil(this.total() / this.size); }
  prev() { if (this.page() > 1) { this.page.update(p => p - 1); this.load(); } }
  next() { if (this.page() < this.totalPages) { this.page.update(p => p + 1); this.load(); } }

  openEdit(c: Cliente) {
    this.editTarget = c;
    this.editForm = { nombre: c.nombre, correo: c.correo ?? '', cc: c.cc ?? '', saldo: c.saldo, vip: c.vip, codigo_vip: c.codigo_vip ?? '' };
  }

  saveEdit() {
    if (!this.editTarget) return;
    this.svc.update(this.editTarget.id, this.editForm).subscribe(() => {
      this.editTarget = null;
      this.load();
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
