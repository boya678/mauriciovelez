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
    let remaining = 4;
    const done = () => { remaining--; if (remaining === 0) this.loading.set(false); };

    const statsArr: Stat[] = [];

    this.conversationsService.list('waiting_human', 1, 200).subscribe({
      next: (list) => { statsArr[0] = { label: 'Esperando agente', value: list.length, badge: 'badge-yellow' }; done(); },
      error: () => done(),
    });

    this.conversationsService.list('human_active', 1, 200).subscribe({
      next: (list) => { statsArr[1] = { label: 'Con agente', value: list.length, badge: 'badge-green' }; done(); this.stats.set(statsArr.filter(Boolean)); },
      error: () => done(),
    });

    this.conversationsService.list('bot_active', 1, 200).subscribe({
      next: (list) => { statsArr[2] = { label: 'Bot activo', value: list.length, badge: 'badge-blue' }; done(); this.stats.set(statsArr.filter(Boolean)); },
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
        done();
        this.stats.set([
          ...statsArr.filter(Boolean),
          { label: 'Agentes en línea', value: list.filter(a => a.status === 'online').length, badge: 'badge-green' },
        ]);
      },
      error: () => done(),
    });
  }
}
