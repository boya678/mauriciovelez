import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { ConversationsService } from '../../../core/services/conversations.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { AuthService } from '../../../core/services/auth.service';
import { Conversation, ConversationStatus, STATUS_LABELS, STATUS_BADGE } from '../../../core/models/conversation.model';
import { ChatComponent } from '../chat/chat.component';

type Tab = 'waiting' | 'mine' | 'bot';

const TAB_STATUS: Record<Tab, ConversationStatus> = {
  waiting: 'waiting_human',
  mine: 'human_active',
  bot: 'bot_active',
};

@Component({
  selector: 'app-inbox',
  standalone: true,
  imports: [CommonModule, ChatComponent],
  templateUrl: './inbox.component.html',
  styleUrl: './inbox.component.scss',
})
export class InboxComponent implements OnInit, OnDestroy {
  activeTab = signal<Tab>('waiting');
  conversations = signal<Conversation[]>([]);
  selectedId = signal<string | null>(null);
  loading = signal(false);

  readonly STATUS_LABELS = STATUS_LABELS;
  readonly STATUS_BADGE = STATUS_BADGE;

  private wsSub?: Subscription;

  constructor(
    private conversationsService: ConversationsService,
    private ws: WebSocketService,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    this.fetchConversations();

    this.wsSub = this.ws.events$.subscribe((ev) => {
      if (
        ev.type === 'new_message' ||
        ev.type === 'conversation_assigned' ||
        ev.type === 'conversation_closed' ||
        ev.type === 'conversation_waiting'
      ) {
        this.fetchConversations();
      }
    });
  }

  fetchConversations(): void {
    this.loading.set(true);
    const status = TAB_STATUS[this.activeTab()];
    this.conversationsService.list(status).subscribe({
      next: (list) => {
        // For "mine" tab, filter by assigned agent
        if (this.activeTab() === 'mine') {
          const myId = this.auth.getAgentId();
          console.log('[inbox] myId:', myId, 'assigned_agent_ids:', list.map(c => c.assigned_agent_id));
          this.conversations.set(list.filter((c) => c.assigned_agent_id === myId));
        } else {
          this.conversations.set(list);
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  selectTab(tab: Tab): void {
    this.activeTab.set(tab);
    this.selectedId.set(null);
    this.fetchConversations();
  }

  selectConversation(id: string): void {
    console.log('[inbox] selectConversation', id);
    this.selectedId.set(id);
  }

  formatDate(iso: string): string {
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('es', { day: '2-digit', month: 'short' });
  }

  ngOnDestroy(): void {
    this.wsSub?.unsubscribe();
  }
}
