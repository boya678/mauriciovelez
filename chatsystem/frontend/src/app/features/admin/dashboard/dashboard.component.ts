import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConversationsService } from '../../../core/services/conversations.service';
import { AgentsApiService, MessageStatsRow } from '../../../core/services/agents-api.service';
import { Agent } from '../../../core/models/agent.model';
import { TokenUsageRow } from '../../../core/services/superadmin-api.service';

const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

interface Stat { label: string; value: number; badge: string; }

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  stats = signal<Stat[]>([]);
  agents = signal<Agent[]>([]);
  loading = signal(true);
  usageRows = signal<TokenUsageRow[]>([]);
  usageLoading = signal(false);
  msgRows = signal<MessageStatsRow[]>([]);
  msgLoading = signal(false);

  constructor(
    private conversationsService: ConversationsService,
    private agentsApi: AgentsApiService
  ) {}

  ngOnInit(): void {
    this.load();
  }

  monthLabel(m: number): string { return MONTHS[m - 1] ?? String(m); }
  usageTotal(f: 'in' | 'out' | 'total'): number {
    return this.usageRows().reduce((a, r) => a + (f === 'in' ? r.tokens_in : f === 'out' ? r.tokens_out : r.tokens_total), 0);
  }
  msgTotal(f: 'bot' | 'human' | 'user'): number {
    return this.msgRows().reduce((a, r) => a + (f === 'bot' ? r.bot_messages : f === 'human' ? r.human_messages : r.user_messages), 0);
  }
  fmt(n: number): string { return n.toLocaleString('es-CO'); }

  private load(): void {
    let remaining = 2;
    const done = () => { remaining--; if (remaining === 0) this.loading.set(false); };

    const statsArr: Stat[] = [];
    let onlineAgentsStat: Stat | null = null;
    const publish = () => this.stats.set([...statsArr.filter(Boolean), ...(onlineAgentsStat ? [onlineAgentsStat] : [])]);

    this.conversationsService.counts().subscribe({
      next: (counts) => {
        statsArr[0] = { label: 'Esperando agente', value: counts['waiting_human'] ?? 0, badge: 'badge-yellow' };
        statsArr[1] = { label: 'Con agente', value: counts['human_active'] ?? 0, badge: 'badge-green' };
        statsArr[2] = { label: 'Bot activo', value: counts['bot_active'] ?? 0, badge: 'badge-blue' };
        publish();
        done();
      },
      error: () => done(),
    });

    this.usageLoading.set(true);
    this.agentsApi.getTokenUsageMy(6).subscribe({
      next: rows => { this.usageRows.set(rows); this.usageLoading.set(false); },
      error: () => this.usageLoading.set(false),
    });

    this.msgLoading.set(true);
    this.agentsApi.getMessageStatsMy(6).subscribe({
      next: rows => { this.msgRows.set(rows); this.msgLoading.set(false); },
      error: () => this.msgLoading.set(false),
    });

    this.agentsApi.list().subscribe({
      next: (list) => {
        this.agents.set(list);
        onlineAgentsStat = { label: 'Agentes en línea', value: list.filter(a => a.status === 'online').length, badge: 'badge-green' };
        publish();
        done();
      },
      error: () => done(),
    });
  }
}
