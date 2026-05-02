import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConversationsService } from '../../../core/services/conversations.service';
import { AgentsApiService } from '../../../core/services/agents-api.service';
import { Agent } from '../../../core/models/agent.model';

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

  constructor(
    private conversationsService: ConversationsService,
    private agentsApi: AgentsApiService
  ) {}

  ngOnInit(): void {
    this.load();
  }

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
