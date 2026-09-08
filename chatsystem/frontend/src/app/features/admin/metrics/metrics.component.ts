import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  AgentMetricRow,
  AgentMetricsResponse,
  AgentMetricsService,
} from '../../../core/services/agent-metrics.service';

interface TeamSummary {
  assigned: number;
  handled: number;
  closed: number;
  active: number;
  messages: number;
  unread: number;
  firstResponse: number | null;
}

@Component({
  selector: 'app-metrics',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './metrics.component.html',
  styleUrl: './metrics.component.scss',
})
export class MetricsComponent implements OnInit {
  metrics = signal<AgentMetricsResponse | null>(null);
  agentOptions = signal<AgentMetricRow[]>([]);
  loading = signal(false);
  error = signal('');

  fromDate = this.isoDate(this.shiftDays(new Date(), -29));
  toDate = this.isoDate(new Date());
  selectedAgentId = '';

  summary = computed<TeamSummary>(() => {
    const rows = this.metrics()?.agents ?? [];
    return {
      assigned: this.sum(rows, 'assigned_conversations'),
      handled: this.sum(rows, 'handled_conversations'),
      closed: this.sum(rows, 'closed_conversations'),
      active: this.sum(rows, 'active_conversations'),
      messages: this.sum(rows, 'human_messages'),
      unread: this.sum(rows, 'unread_messages'),
      firstResponse: this.weightedAverage(
        rows,
        'avg_first_response_seconds',
        'first_response_samples'
      ),
    };
  });

  maxDaily = computed(() => Math.max(
    1,
    ...(this.metrics()?.daily ?? []).flatMap((row) => [
      row.assigned_conversations,
      row.closed_conversations,
      row.human_messages,
    ])
  ));

  constructor(private agentMetrics: AgentMetricsService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    if (!this.fromDate || !this.toDate || this.fromDate > this.toDate) {
      this.error.set('Selecciona un rango de fechas válido.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.agentMetrics.getMetrics(
      this.fromDate,
      this.toDate,
      this.selectedAgentId || undefined
    ).subscribe({
      next: (response) => {
        this.metrics.set(response);
        if (!this.selectedAgentId || this.agentOptions().length === 0) {
          this.agentOptions.set(response.agents);
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail || 'No fue posible cargar las métricas.');
        this.loading.set(false);
      },
    });
  }

  exportCsv(): void {
    const rows = this.metrics()?.agents ?? [];
    if (rows.length === 0) return;
    const header = [
      'Agente', 'Correo', 'Asignadas', 'Atendidas', 'Cerradas', 'Activas',
      'Mensajes', 'Pendientes', 'Primera respuesta', 'Respuesta promedio',
      'Resolución promedio', 'Liberadas o reasignadas',
    ];
    const data = rows.map((row) => [
      row.name,
      row.email,
      row.assigned_conversations,
      row.handled_conversations,
      row.closed_conversations,
      row.active_conversations,
      row.human_messages,
      row.unread_messages,
      this.formatDuration(row.avg_first_response_seconds),
      this.formatDuration(row.avg_response_seconds),
      this.formatDuration(row.avg_resolution_seconds),
      row.released_conversations,
    ]);
    const csv = [header, ...data]
      .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(';'))
      .join('\r\n');
    const url = URL.createObjectURL(new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `metricas-agentes-${this.fromDate}-${this.toDate}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  barHeight(value: number): number {
    return Math.max(value > 0 ? 4 : 0, Math.round((value / this.maxDaily()) * 100));
  }

  formatDay(value: string): string {
    return new Date(`${value}T00:00:00`).toLocaleDateString('es-CO', {
      day: '2-digit',
      month: 'short',
    });
  }

  formatDuration(seconds: number | null): string {
    if (seconds == null || !Number.isFinite(seconds)) return 'Sin datos';
    const rounded = Math.max(0, Math.round(seconds));
    if (rounded < 60) return `${rounded} s`;
    if (rounded < 3600) return `${Math.floor(rounded / 60)} min ${rounded % 60} s`;
    const hours = Math.floor(rounded / 3600);
    const minutes = Math.floor((rounded % 3600) / 60);
    return `${hours} h ${minutes} min`;
  }

  formatNumber(value: number): string {
    return value.toLocaleString('es-CO');
  }

  private sum(rows: AgentMetricRow[], key: keyof AgentMetricRow): number {
    return rows.reduce((total, row) => total + Number(row[key] || 0), 0);
  }

  private weightedAverage(
    rows: AgentMetricRow[],
    valueKey: keyof AgentMetricRow,
    samplesKey: keyof AgentMetricRow
  ): number | null {
    let total = 0;
    let samples = 0;
    for (const row of rows) {
      const value = row[valueKey];
      const rowSamples = Number(row[samplesKey] || 0);
      if (typeof value === 'number' && rowSamples > 0) {
        total += value * rowSamples;
        samples += rowSamples;
      }
    }
    return samples > 0 ? total / samples : null;
  }

  private shiftDays(value: Date, days: number): Date {
    const copy = new Date(value);
    copy.setDate(copy.getDate() + days);
    return copy;
  }

  private isoDate(value: Date): string {
    const offset = value.getTimezoneOffset() * 60_000;
    return new Date(value.getTime() - offset).toISOString().slice(0, 10);
  }
}