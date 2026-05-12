import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentsApiService } from '../../../core/services/agents-api.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent implements OnInit {
  promptText = '';
  templateName = '';
  templateLanguage = 'es';
  loading = signal(true);
  saving = signal(false);
  saved = signal(false);
  error = signal<string | null>(null);

  // Knowledge base
  knowledgeText = '';
  knowledgeChunks = signal<number | null>(null);
  knowledgeSaving = signal(false);
  knowledgeSaved = signal(false);
  knowledgeDeleting = signal(false);
  knowledgeError = signal<string | null>(null);

  constructor(private agentsApi: AgentsApiService) {}

  ngOnInit(): void {
    this.agentsApi.getSettings().subscribe({
      next: (s) => {
        this.promptText = s.ai_system_prompt ?? '';
        this.templateName = s.whatsapp_template_name ?? '';
        this.templateLanguage = s.whatsapp_template_language ?? 'es';
        this.loading.set(false);
      },
      error: () => {
        this.error.set('No se pudo cargar la configuración.');
        this.loading.set(false);
      },
    });

    this.agentsApi.getKnowledgeStatus().subscribe({
      next: (s) => this.knowledgeChunks.set(s.chunks),
      error: () => this.knowledgeChunks.set(0),
    });
  }

  save(): void {
    this.saving.set(true);
    this.saved.set(false);
    this.error.set(null);
    this.agentsApi.updateSettings({
      ai_system_prompt: this.promptText || null,
      whatsapp_template_name: this.templateName || null,
      whatsapp_template_language: this.templateLanguage || null,
    }).subscribe({
      next: () => {
        this.saving.set(false);
        this.saved.set(true);
        setTimeout(() => this.saved.set(false), 3000);
      },
      error: () => {
        this.saving.set(false);
        this.error.set('Error al guardar. Intenta de nuevo.');
      },
    });
  }

  saveKnowledge(): void {
    if (!this.knowledgeText.trim()) return;
    this.knowledgeSaving.set(true);
    this.knowledgeSaved.set(false);
    this.knowledgeError.set(null);
    this.agentsApi.uploadKnowledge(this.knowledgeText).subscribe({
      next: (res) => {
        this.knowledgeSaving.set(false);
        this.knowledgeSaved.set(true);
        this.knowledgeChunks.set(res.chunks);
        this.knowledgeText = '';
        setTimeout(() => this.knowledgeSaved.set(false), 3000);
      },
      error: () => {
        this.knowledgeSaving.set(false);
        this.knowledgeError.set('Error al guardar el conocimiento. Intenta de nuevo.');
      },
    });
  }

  deleteKnowledge(): void {
    if (!confirm('¿Eliminar toda la base de conocimiento? Esta acción no se puede deshacer.')) return;
    this.knowledgeDeleting.set(true);
    this.knowledgeError.set(null);
    this.agentsApi.deleteKnowledge().subscribe({
      next: () => {
        this.knowledgeDeleting.set(false);
        this.knowledgeChunks.set(0);
      },
      error: () => {
        this.knowledgeDeleting.set(false);
        this.knowledgeError.set('Error al eliminar. Intenta de nuevo.');
      },
    });
  }
}
