import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentsApiService } from '../../../core/services/agents-api.service';
import { Agent, AgentCreate, AgentRole, AgentUpdate } from '../../../core/models/agent.model';

interface AgentForm {
  name: string;
  email: string;
  password: string;
  role: AgentRole;
  max_concurrent_chats: number;
}

@Component({
  selector: 'app-agents-mgmt',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agents-mgmt.component.html',
  styleUrl: './agents-mgmt.component.scss',
})
export class AgentsMgmtComponent implements OnInit {
  agents = signal<Agent[]>([]);
  loading = signal(false);
  saving = signal(false);
  error = signal('');

  showModal = signal(false);
  editAgent = signal<Agent | null>(null);
  confirmDeleteId = signal<string | null>(null);

  form: AgentForm = this.emptyForm();

  readonly roles: AgentRole[] = ['agent', 'admin', 'superadmin'];

  constructor(private agentsApi: AgentsApiService) {}

  ngOnInit(): void {
    this.fetch();
  }

  private fetch(): void {
    this.loading.set(true);
    this.agentsApi.list().subscribe({
      next: (list) => { this.agents.set(list); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  private emptyForm(): AgentForm {
    return { name: '', email: '', password: '', role: 'agent', max_concurrent_chats: 3 };
  }

  openCreate(): void {
    this.form = this.emptyForm();
    this.editAgent.set(null);
    this.error.set('');
    this.showModal.set(true);
  }

  openEdit(agent: Agent): void {
    this.form = {
      name: agent.name,
      email: agent.email,
      password: '',
      role: agent.role,
      max_concurrent_chats: agent.max_concurrent_chats,
    };
    this.editAgent.set(agent);
    this.error.set('');
    this.showModal.set(true);
  }

  closeModal(): void {
    this.showModal.set(false);
    this.editAgent.set(null);
  }

  save(): void {
    if (!this.form.name || !this.form.email) {
      this.error.set('Nombre y email son requeridos.');
      return;
    }

    this.saving.set(true);
    this.error.set('');

    const editing = this.editAgent();
    const obs = editing
      ? this.agentsApi.update(editing.id, {
          name: this.form.name,
          role: this.form.role,
          max_concurrent_chats: this.form.max_concurrent_chats,
          ...(this.form.password ? { password: this.form.password } : {}),
        } satisfies AgentUpdate)
      : this.agentsApi.create({
          name: this.form.name,
          email: this.form.email,
          password: this.form.password,
          role: this.form.role,
          max_concurrent_chats: this.form.max_concurrent_chats,
        } satisfies AgentCreate);

    obs.subscribe({
      next: () => {
        this.saving.set(false);
        this.closeModal();
        this.fetch();
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(err?.error?.detail ?? 'Error al guardar.');
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
    this.agentsApi.delete(id).subscribe({
      next: () => { this.confirmDeleteId.set(null); this.fetch(); },
      error: () => this.confirmDeleteId.set(null),
    });
  }
}
