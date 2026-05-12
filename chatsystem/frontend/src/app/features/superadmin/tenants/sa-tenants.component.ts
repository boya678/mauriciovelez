import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SuperadminApiService } from '../../../core/services/superadmin-api.service';
import { TenantCreate, TenantOut, TenantUpdate } from '../../../core/models/tenant.model';

@Component({
  selector: 'app-sa-tenants',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sa-tenants.component.html',
  styleUrl: './sa-tenants.component.scss',
})
export class SaTenantsComponent implements OnInit {
  tenants = signal<TenantOut[]>([]);
  loading = signal(false);
  saving = signal(false);
  error = signal('');
  showModal = signal(false);
  editTenant = signal<TenantOut | null>(null);

  // Knowledge management
  knowledgeTenant = signal<TenantOut | null>(null);
  knowledgeText = signal('');
  knowledgeChunks = signal<number | null>(null);
  knowledgeLoading = signal(false);
  knowledgeSaving = signal(false);
  knowledgeError = signal('');
  showKnowledgeModal = signal(false);

  form: TenantCreate = this.emptyForm();

  constructor(private api: SuperadminApiService) {}

  ngOnInit(): void {
    this.fetch();
  }

  private fetch(): void {
    this.loading.set(true);
    this.api.listTenants().subscribe({
      next: list => { this.tenants.set(list); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  private emptyForm(): TenantCreate {
    return { name: '', slug: '', whatsapp_phone_id: null, whatsapp_token: null, webhook_secret: null, ai_system_prompt: null, whatsapp_template_name: null, whatsapp_template_language: null };
  }

  openCreate(): void {
    this.form = this.emptyForm();
    this.editTenant.set(null);
    this.error.set('');
    this.showModal.set(true);
  }

  openEdit(t: TenantOut): void {
    this.form = {
      name: t.name,
      slug: t.slug,
      whatsapp_phone_id: t.whatsapp_phone_id,
      whatsapp_token: t.whatsapp_token,
      webhook_secret: t.webhook_secret,
      ai_system_prompt: t.ai_system_prompt,
      whatsapp_template_name: t.whatsapp_template_name,
      whatsapp_template_language: t.whatsapp_template_language,
    };
    this.editTenant.set(t);
    this.error.set('');
    this.showModal.set(true);
  }

  closeModal(): void {
    this.showModal.set(false);
    this.editTenant.set(null);
  }

  save(): void {
    if (!this.form.name) { this.error.set('El nombre es requerido.'); return; }
    const editing = this.editTenant();
    if (!editing && !this.form.slug) { this.error.set('El slug es requerido.'); return; }

    this.saving.set(true);
    this.error.set('');

    const obs = editing
      ? this.api.updateTenant(editing.id, {
          name: this.form.name,
          whatsapp_phone_id: this.form.whatsapp_phone_id,
          whatsapp_token: this.form.whatsapp_token,
          webhook_secret: this.form.webhook_secret,
          ai_system_prompt: this.form.ai_system_prompt,
          whatsapp_template_name: this.form.whatsapp_template_name,
          whatsapp_template_language: this.form.whatsapp_template_language,
        } satisfies TenantUpdate)
      : this.api.createTenant(this.form);

    obs.subscribe({
      next: () => { this.saving.set(false); this.closeModal(); this.fetch(); },
      error: (e) => {
        this.error.set(e?.error?.detail ?? 'Error al guardar.');
        this.saving.set(false);
      },
    });
  }

  // ── Knowledge management ──────────────────────────────────────────────────

  openKnowledge(t: TenantOut): void {
    this.knowledgeTenant.set(t);
    this.knowledgeText.set('');
    this.knowledgeChunks.set(null);
    this.knowledgeError.set('');
    this.showKnowledgeModal.set(true);
    this.knowledgeLoading.set(true);
    this.api.getKnowledgeStatus(t.id).subscribe({
      next: (s) => { this.knowledgeChunks.set(s.chunks); this.knowledgeLoading.set(false); },
      error: () => this.knowledgeLoading.set(false),
    });
  }

  closeKnowledgeModal(): void {
    this.showKnowledgeModal.set(false);
    this.knowledgeTenant.set(null);
  }

  saveKnowledge(): void {
    const t = this.knowledgeTenant();
    if (!t) return;
    const text = this.knowledgeText().trim();
    if (!text) { this.knowledgeError.set('Pega el texto del documento primero.'); return; }

    this.knowledgeSaving.set(true);
    this.knowledgeError.set('');
    this.api.uploadKnowledge(t.id, text).subscribe({
      next: (res) => {
        this.knowledgeChunks.set(res.chunks);
        this.knowledgeText.set('');
        this.knowledgeSaving.set(false);
      },
      error: (e) => {
        this.knowledgeError.set(e?.error?.detail ?? 'Error al cargar el conocimiento.');
        this.knowledgeSaving.set(false);
      },
    });
  }

  deleteKnowledge(): void {
    const t = this.knowledgeTenant();
    if (!t) return;
    this.knowledgeSaving.set(true);
    this.knowledgeError.set('');
    this.api.deleteKnowledge(t.id).subscribe({
      next: () => {
        this.knowledgeChunks.set(0);
        this.knowledgeSaving.set(false);
      },
      error: (e) => {
        this.knowledgeError.set(e?.error?.detail ?? 'Error al eliminar el conocimiento.');
        this.knowledgeSaving.set(false);
      },
    });
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });
  }
}
