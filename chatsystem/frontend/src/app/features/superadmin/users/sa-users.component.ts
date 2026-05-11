import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SuperadminApiService } from '../../../core/services/superadmin-api.service';
import { SuperadminUser } from '../../../core/models/superadmin.model';
import { SuperadminAuthService } from '../../../core/services/superadmin-auth.service';

interface UserForm {
  name: string;
  email: string;
  password: string;
}

@Component({
  selector: 'app-sa-users',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sa-users.component.html',
  styleUrl: './sa-users.component.scss',
})
export class SaUsersComponent implements OnInit {
  users = signal<SuperadminUser[]>([]);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  showModal = signal(false);
  confirmDeleteId = signal<string | null>(null);
  myId = '';

  form: UserForm = this.emptyForm();

  constructor(private api: SuperadminApiService, private auth: SuperadminAuthService) {}

  ngOnInit(): void {
    this.myId = this.auth.getPayload()?.['sub'] ?? '';
    this.fetch();
  }

  private fetch(): void {
    this.loading.set(true);
    this.api.listUsers().subscribe({
      next: list => { this.users.set(list); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  private emptyForm(): UserForm {
    return { name: '', email: '', password: '' };
  }

  openCreate(): void {
    this.form = this.emptyForm();
    this.error.set('');
    this.showModal.set(true);
  }

  closeModal(): void {
    this.showModal.set(false);
  }

  save(): void {
    if (!this.form.name || !this.form.email || !this.form.password) {
      this.error.set('Todos los campos son requeridos.');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    this.api.createUser(this.form).subscribe({
      next: () => { this.saving.set(false); this.closeModal(); this.fetch(); },
      error: (e) => {
        this.error.set(e?.error?.detail ?? 'Error al guardar.');
        this.saving.set(false);
      },
    });
  }

  requestDelete(id: string): void {
    this.confirmDeleteId.set(id);
  }

  cancelDelete(): void {
    this.confirmDeleteId.set(null);
  }

  confirmDelete(id: string): void {
    this.api.deleteUser(id).subscribe({
      next: () => { this.confirmDeleteId.set(null); this.fetch(); },
      error: () => this.confirmDeleteId.set(null),
    });
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });
  }
}
