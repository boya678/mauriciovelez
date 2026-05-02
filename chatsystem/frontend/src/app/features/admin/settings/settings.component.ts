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
  loading = signal(true);
  saving = signal(false);
  saved = signal(false);
  error = signal<string | null>(null);

  constructor(private agentsApi: AgentsApiService) {}

  ngOnInit(): void {
    this.agentsApi.getSettings().subscribe({
      next: (s) => {
        this.promptText = s.ai_system_prompt ?? '';
        this.loading.set(false);
      },
      error: () => {
        this.error.set('No se pudo cargar la configuración.');
        this.loading.set(false);
      },
    });
  }

  save(): void {
    this.saving.set(true);
    this.saved.set(false);
    this.error.set(null);
    this.agentsApi.updateSettings(this.promptText || null).subscribe({
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
}
