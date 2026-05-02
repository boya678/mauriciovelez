import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentTool, AgentToolCreate, ToolType, ToolsApiService } from '../../../core/services/tools-api.service';

interface ToolForm {
  name: string;
  description: string;
  tool_type: ToolType;
  enabled: boolean;
  // HTTP
  http_url: string;
  http_method: string;
  http_headers: string; // JSON string
  http_body_tpl: string;
  http_timeout_seconds: number;
  // SQL
  sql_dsn: string;
  sql_query: string;
  sql_params: string; // comma-separated
  // STATIC
  static_text: string;
}

@Component({
  selector: 'app-tools',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './tools.component.html',
  styleUrl: './tools.component.scss',
})
export class ToolsComponent implements OnInit {
  tools = signal<AgentTool[]>([]);
  loading = signal(false);
  saving = signal(false);
  error = signal('');

  showModal = signal(false);
  editTool = signal<AgentTool | null>(null);
  confirmDeleteId = signal<string | null>(null);

  // Test panel
  testToolId = signal<string | null>(null);
  testParams = signal<{ key: string; value: string }[]>([]);
  testLoading = signal(false);
  testResult = signal<string | null>(null);

  form: ToolForm = this.emptyForm();

  readonly methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
  readonly toolTypes: ToolType[] = ['HTTP', 'SQL', 'STATIC'];

  constructor(private toolsApi: ToolsApiService) {}

  ngOnInit(): void {
    this.fetch();
  }

  private fetch(): void {
    this.loading.set(true);
    this.toolsApi.list().subscribe({
      next: (list) => { this.tools.set(list); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  private emptyForm(): ToolForm {
    return {
      name: '',
      description: '',
      tool_type: 'HTTP',
      enabled: true,
      http_url: '',
      http_method: 'POST',
      http_headers: '',
      http_body_tpl: '',
      http_timeout_seconds: 10,
      sql_dsn: '',
      sql_query: '',
      sql_params: '',
      static_text: '',
    };
  }

  openCreate(): void {
    this.form = this.emptyForm();
    this.editTool.set(null);
    this.error.set('');
    this.showModal.set(true);
  }

  openEdit(tool: AgentTool): void {
    this.form = {
      name: tool.name,
      description: tool.description,
      tool_type: tool.tool_type,
      enabled: tool.enabled,
      http_url: tool.http_url ?? '',
      http_method: tool.http_method ?? 'POST',
      http_headers: tool.http_headers ? JSON.stringify(tool.http_headers, null, 2) : '',
      http_body_tpl: tool.http_body_tpl ?? '',
      http_timeout_seconds: tool.http_timeout_seconds ?? 10,
      sql_dsn: tool.sql_dsn ?? '',
      sql_query: tool.sql_query ?? '',
      sql_params: (tool.sql_params ?? []).join(', '),
      static_text: tool.static_text ?? '',
    };
    this.editTool.set(tool);
    this.error.set('');
    this.showModal.set(true);
  }

  closeModal(): void {
    this.showModal.set(false);
    this.editTool.set(null);
  }

  save(): void {
    if (!this.form.name.trim()) {
      this.error.set('El nombre es requerido.');
      return;
    }

    let headers: Record<string, string> | null = null;
    if (this.form.http_headers.trim()) {
      try {
        headers = JSON.parse(this.form.http_headers);
      } catch {
        this.error.set('HTTP Headers no es JSON válido.');
        return;
      }
    }

    const payload: AgentToolCreate = {
      name: this.form.name.trim(),
      description: this.form.description.trim(),
      tool_type: this.form.tool_type,
      enabled: this.form.enabled,
      http_url: this.form.tool_type === 'HTTP' ? (this.form.http_url || null) : null,
      http_method: this.form.tool_type === 'HTTP' ? (this.form.http_method || null) : null,
      http_headers: this.form.tool_type === 'HTTP' ? headers : null,
      http_body_tpl: this.form.tool_type === 'HTTP' ? (this.form.http_body_tpl || null) : null,
      http_timeout_seconds: this.form.tool_type === 'HTTP' ? this.form.http_timeout_seconds : null,
      sql_dsn: this.form.tool_type === 'SQL' ? (this.form.sql_dsn || null) : null,
      sql_query: this.form.tool_type === 'SQL' ? (this.form.sql_query || null) : null,
      sql_params: this.form.tool_type === 'SQL'
        ? this.form.sql_params.split(',').map(s => s.trim()).filter(Boolean)
        : null,
      static_text: this.form.tool_type === 'STATIC' ? (this.form.static_text || null) : null,
    };

    this.saving.set(true);
    this.error.set('');

    const editing = this.editTool();
    const obs = editing
      ? this.toolsApi.update(editing.id, payload)
      : this.toolsApi.create(payload);

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
    this.toolsApi.delete(id).subscribe({
      next: () => {
        this.confirmDeleteId.set(null);
        this.fetch();
      },
    });
  }

  toggleEnabled(tool: AgentTool): void {
    this.toolsApi.update(tool.id, { enabled: !tool.enabled }).subscribe({
      next: () => this.fetch(),
    });
  }

  // Test panel
  openTest(tool: AgentTool): void {
    this.testToolId.set(tool.id);
    const params = (tool.sql_params ?? []).map(k => ({ key: k, value: '' }));
    // For HTTP tools, start with an empty param row
    if (tool.tool_type === 'HTTP' && params.length === 0) {
      params.push({ key: '', value: '' });
    }
    this.testParams.set(params);
    this.testResult.set(null);
  }

  closeTest(): void {
    this.testToolId.set(null);
    this.testResult.set(null);
  }

  addTestParam(): void {
    this.testParams.update(p => [...p, { key: '', value: '' }]);
  }

  removeTestParam(i: number): void {
    this.testParams.update(p => p.filter((_, idx) => idx !== i));
  }

  runTest(): void {
    const id = this.testToolId();
    if (!id) return;

    const params: Record<string, string> = {};
    for (const p of this.testParams()) {
      if (p.key.trim()) params[p.key.trim()] = p.value;
    }

    this.testLoading.set(true);
    this.testResult.set(null);

    this.toolsApi.test(id, params).subscribe({
      next: (r) => { this.testResult.set(r.result); this.testLoading.set(false); },
      error: (err) => {
        this.testResult.set('Error: ' + (err?.error?.detail ?? err.message));
        this.testLoading.set(false);
      },
    });
  }

  trackByIdx(i: number): number { return i; }
}
