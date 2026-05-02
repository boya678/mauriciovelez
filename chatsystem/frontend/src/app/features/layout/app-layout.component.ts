import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { AgentsApiService } from '../../core/services/agents-api.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { AgentStatus } from '../../core/models/agent.model';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, RouterModule, RouterLink, RouterLinkActive],
  templateUrl: './app-layout.component.html',
  styleUrl: './app-layout.component.scss',
})
export class AppLayoutComponent implements OnInit, OnDestroy {
  agentStatus = signal<AgentStatus>('online');
  agentName = signal('');
  isAdmin = signal(false);

  private heartbeatRef?: ReturnType<typeof setInterval>;

  constructor(
    public auth: AuthService,
    private agentsApi: AgentsApiService,
    private ws: WebSocketService
  ) {}

  ngOnInit(): void {
    this.isAdmin.set(this.auth.isAdmin());
    this.ws.connect();

    this.agentsApi.getMe().subscribe({
      next: (me) => {
        this.agentName.set(me.name);
        this.agentStatus.set(me.status);
      },
    });

    // When WS connects, backend marks agent ONLINE — reflect that immediately
    this.ws.connected$.subscribe(() => this.agentStatus.set('online'));

    // Heartbeat every 60s so the backend marks the agent online
    this.heartbeatRef = setInterval(() => {
      this.agentsApi.heartbeat().subscribe();
    }, 60_000);
  }

  toggleStatus(): void {
    const next: AgentStatus = this.agentStatus() === 'online' ? 'offline' : 'online';
    this.agentsApi.setStatus(next).subscribe(() => this.agentStatus.set(next));
  }

  logout(): void {
    this.ws.disconnect();
    this.auth.logout();
  }

  ngOnDestroy(): void {
    clearInterval(this.heartbeatRef);
    this.ws.disconnect();
  }
}
