import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { UsuariosService, PlatformUser } from '../../core/services/usuarios.service';
import { AuthService } from '../../core/services/auth.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-usuarios',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './usuarios.component.html',
  styleUrl: './usuarios.component.scss',
})
export class UsuariosComponent implements OnInit {
  items = signal<PlatformUser[]>([]);
  loading = signal(false);

  showCreate = false;
  editTarget: PlatformUser | null = null;
  deleteTarget: PlatformUser | null = null;

  createForm = { cc: '', nombre: '', usuario: '', clave: '', role: 'reader' };
  editForm: { cc?: string; nombre?: string; role?: string; active?: boolean; clave?: string } = {};

  roles = ['admin', 'edit', 'reader'];

  constructor(private svc: UsuariosService, public auth: AuthService, private router: Router) {}

  ngOnInit() {
    if (!this.auth.isAdmin()) { this.router.navigate(['/admin/clientes']); return; }
    this.load();
  }

  load() {
    this.loading.set(true);
    this.svc.list().subscribe(res => { this.items.set(res); this.loading.set(false); });
  }

  openCreate() {
    this.createForm = { cc: '', nombre: '', usuario: '', clave: '', role: 'reader' };
    this.showCreate = true;
  }

  submitCreate() {
    this.svc.create(this.createForm).subscribe({ next: () => { this.showCreate = false; this.load(); }, error: e => alert(e.error?.detail || 'Error') });
  }

  openEdit(u: PlatformUser) {
    this.editTarget = u;
    this.editForm = { cc: u.cc, nombre: u.nombre, role: u.role, active: u.active, clave: '' };
  }

  submitEdit() {
    if (!this.editTarget) return;
    const data = { ...this.editForm };
    if (!data.clave) delete data.clave;
    this.svc.update(this.editTarget.id, data).subscribe({ next: () => { this.editTarget = null; this.load(); }, error: e => alert(e.error?.detail || 'Error') });
  }

  openDelete(u: PlatformUser) { this.deleteTarget = u; }

  confirmDelete() {
    if (!this.deleteTarget) return;
    this.svc.delete(this.deleteTarget.id).subscribe({ next: () => { this.deleteTarget = null; this.load(); }, error: e => alert(e.error?.detail || 'Error') });
  }
}
