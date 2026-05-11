import { Component, OnDestroy, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { ConversationsService } from '../../../core/services/conversations.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { AuthService } from '../../../core/services/auth.service';
import { Conversation, ConversationStatus, STATUS_LABELS, STATUS_BADGE } from '../../../core/models/conversation.model';
import { ChatComponent } from '../chat/chat.component';

type Tab = 'waiting' | 'mine' | 'bot' | 'closed';

const TAB_STATUS: Record<Tab, ConversationStatus | null> = {
  waiting: 'waiting_human',
  mine: 'human_active',
  bot: 'bot_active',
  closed: 'closed',
};

@Component({
  selector: 'app-inbox',
  standalone: true,
  imports: [CommonModule, FormsModule, ChatComponent],
  templateUrl: './inbox.component.html',
  styleUrl: './inbox.component.scss',
})
export class InboxComponent implements OnInit, OnDestroy {
  activeTab = signal<Tab>('waiting');
  conversations = signal<Conversation[]>([]);
  selectedId = signal<string | null>(null);
  loading = signal(false);
  searchTerm = signal('');

  // New conversation modal
  newConvModal = signal(false);
  newConvPhone = '';
  newConvStep = signal<'form' | 'confirm' | 'bot_active' | 'human_active' | 'waiting_human'>('form');
  newConvLoading = signal(false);
  newConvError = signal<string | null>(null);
  newConvBotConvId = signal<string | null>(null);

  filteredConversations = computed(() => {
    const term = this.searchTerm().trim().toLowerCase();
    if (!term) return this.conversations();
    return this.conversations().filter(c => c.phone.toLowerCase().includes(term));
  });

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
        ev.type === 'conversation_waiting' ||
        ev.type === 'conversation_started'
      ) {
        this.fetchConversations();
      }
    });
  }

  fetchConversations(): void {
    this.loading.set(true);
    const status = TAB_STATUS[this.activeTab()];
    this.conversationsService.list(status ?? undefined).subscribe({
      next: (list) => {
        // For "mine" tab, filter by assigned agent
        if (this.activeTab() === 'mine') {
          const myId = this.auth.getAgentId();
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
    this.selectedId.set(id);
  }

  openNewConvModal(): void {
    this.newConvPhone = '';
    this.newConvStep.set('form');
    this.newConvError.set(null);
    this.newConvModal.set(true);
  }

  closeNewConvModal(): void {
    this.newConvModal.set(false);
  }

  confirmNewConv(): void {
    if (!this.newConvPhone.trim()) return;
    this.newConvStep.set('confirm');
  }

  submitNewConv(): void {
    this.newConvLoading.set(true);
    this.newConvError.set(null);
    this.conversationsService.startConversation(this.newConvPhone.trim()).subscribe({
      next: (conv) => {
        this.newConvLoading.set(false);
        this.newConvModal.set(false);
        this.selectTab('mine');
        this.selectedId.set(conv.id);
      },
      error: (err) => {
        this.newConvLoading.set(false);
        const detail = err?.error?.detail;
        if (detail?.code === 'bot_active') {
          this.newConvBotConvId.set(detail.conversation_id);
          this.newConvStep.set('bot_active');
          return;
        }
        if (detail?.code === 'human_active') {
          this.newConvBotConvId.set(detail.conversation_id);
          this.newConvStep.set('human_active');
          return;
        }
        if (detail?.code === 'waiting_human') {
          this.newConvBotConvId.set(detail.conversation_id);
          this.newConvStep.set('waiting_human');
          return;
        }
        this.newConvError.set(typeof detail === 'string' ? detail : 'Error al iniciar la conversación.');
        this.newConvStep.set('form');
      },
    });
  }

  takeoverBot(): void {
    const id = this.newConvBotConvId();
    if (!id) return;
    this.newConvLoading.set(true);
    this.conversationsService.take(id).subscribe({
      next: () => {
        this.newConvLoading.set(false);
        this.newConvModal.set(false);
        this.selectTab('mine');
        this.selectedId.set(id);
      },
      error: () => {
        this.newConvLoading.set(false);
        this.newConvError.set('Error al tomar la conversación.');
        this.newConvStep.set('form');
      },
    });
  }

  takeover(): void {
    const id = this.newConvBotConvId();
    if (!id) return;
    this.newConvLoading.set(true);
    this.conversationsService.take(id).subscribe({
      next: () => {
        this.newConvLoading.set(false);
        this.newConvModal.set(false);
        this.selectTab('mine');
        this.selectedId.set(id);
      },
      error: () => {
        this.newConvLoading.set(false);
        this.newConvError.set('Error al reasignar la conversación.');
        this.newConvStep.set('form');
      },
    });
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
