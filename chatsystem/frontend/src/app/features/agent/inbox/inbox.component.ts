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
  highlightedIds = signal<Set<string>>(new Set());
  mineUnreadTotal = signal(0);

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
  private refreshTimer?: ReturnType<typeof setTimeout>;
  private highlightTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private fetchSequence = 0;
  private audioContext?: AudioContext;
  private readonly unlockNotificationAudio = (): void => {
    try {
      this.audioContext ??= new AudioContext();
      if (this.audioContext.state === 'suspended') {
        void this.audioContext.resume().catch(() => undefined);
      }
    } finally {
      document.removeEventListener('pointerdown', this.unlockNotificationAudio);
      document.removeEventListener('keydown', this.unlockNotificationAudio);
    }
  };

  constructor(
    private conversationsService: ConversationsService,
    private ws: WebSocketService,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    this.fetchConversations();
    this.fetchMineUnreadTotal();
    document.addEventListener('pointerdown', this.unlockNotificationAudio, { once: true });
    document.addEventListener('keydown', this.unlockNotificationAudio, { once: true });

    this.wsSub = this.ws.events$.subscribe((ev) => {
      if (ev.type === 'new_message') {
        this.handleIncomingMessage(ev);
      } else if (ev.type === 'conversation_assigned') {
        this.handleAssignment(ev);
      }
      if (
        ev.type === 'new_message' ||
        ev.type === 'conversation_assigned' ||
        ev.type === 'conversation_closed' ||
        ev.type === 'conversation_waiting' ||
        ev.type === 'conversation_started'
      ) {
        this.scheduleRefresh();
      }
    });
  }

  fetchConversations(showLoading = true): void {
    if (showLoading) this.loading.set(true);
    const requestedTab = this.activeTab();
    const requestSequence = ++this.fetchSequence;
    const status = TAB_STATUS[requestedTab];
    this.conversationsService.list(status ?? undefined).subscribe({
      next: (list) => {
        if (requestSequence !== this.fetchSequence || requestedTab !== this.activeTab()) return;
        // For "mine" tab, filter by assigned agent
        if (requestedTab === 'mine') {
          const myId = this.auth.getAgentId();
          const mine = list.filter((c) => c.assigned_agent_id === myId);
          this.conversations.set(mine);
          this.mineUnreadTotal.set(
            mine.reduce((total, conversation) => total + conversation.unread_count, 0)
          );
        } else {
          this.conversations.set(list);
        }
        this.loading.set(false);
      },
      error: () => {
        if (requestSequence === this.fetchSequence) this.loading.set(false);
      },
    });
  }

  scheduleRefresh(): void {
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => {
      this.refreshTimer = undefined;
      this.fetchConversations(false);
      if (this.activeTab() !== 'mine') this.fetchMineUnreadTotal();
    }, 150);
  }

  private fetchMineUnreadTotal(): void {
    const myId = this.auth.getAgentId();
    this.conversationsService.list('human_active', 1, 500).subscribe({
      next: (list) => this.mineUnreadTotal.set(
        list
          .filter((conversation) => conversation.assigned_agent_id === myId)
          .reduce((total, conversation) => total + conversation.unread_count, 0)
      ),
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

  markConversationRead(id: string): void {
    let readCount = 0;
    this.conversations.update((items) =>
      items.map((conversation) =>
        conversation.id === id
          ? (readCount = conversation.unread_count, { ...conversation, unread_count: 0 })
          : conversation
      )
    );
    if (readCount > 0) {
      this.mineUnreadTotal.update((total) => Math.max(0, total - readCount));
    }
  }

  private handleIncomingMessage(event: Record<string, unknown>): void {
    const conversationId = event['conversation_id'];
    const message = event['message'];
    if (
      typeof conversationId !== 'string' ||
      !message ||
      typeof message !== 'object' ||
      (message as Record<string, unknown>)['sender_type'] !== 'user'
    ) {
      return;
    }

    const knownConversation = this.conversations().find(
      (conversation) => conversation.id === conversationId
    );
    const assignedAgentId = event['assigned_agent_id'] ?? knownConversation?.assigned_agent_id;
    if (assignedAgentId !== this.auth.getAgentId()) return;

    const isOpenAndVisible =
      this.selectedId() === conversationId && document.visibilityState === 'visible';
    if (!isOpenAndVisible) {
      this.mineUnreadTotal.update((total) => total + 1);
      const content = (message as Record<string, unknown>)['content'];
      const createdAt = (message as Record<string, unknown>)['created_at'];
      this.conversations.update((items) =>
        items
          .map((conversation) =>
            conversation.id === conversationId
              ? {
                  ...conversation,
                  unread_count: conversation.unread_count + 1,
                  last_message_preview: typeof content === 'string' ? content : conversation.last_message_preview,
                  last_message_at: typeof createdAt === 'string' ? createdAt : conversation.last_message_at,
                }
              : conversation
          )
          .sort((left, right) =>
            right.unread_count - left.unread_count ||
            Date.parse(right.last_message_at || right.updated_at) -
              Date.parse(left.last_message_at || left.updated_at)
          )
      );
      this.highlightConversation(conversationId);
      this.playNotificationSound();
    }
  }

  private handleAssignment(event: Record<string, unknown>): void {
    const conversationId = event['conversation_id'];
    if (
      typeof conversationId !== 'string' ||
      event['agent_id'] !== this.auth.getAgentId() ||
      this.selectedId() === conversationId
    ) {
      return;
    }
    this.highlightConversation(conversationId);
    this.playNotificationSound();
  }

  private highlightConversation(id: string): void {
    this.highlightedIds.update((ids) => new Set(ids).add(id));
    const currentTimer = this.highlightTimers.get(id);
    if (currentTimer) clearTimeout(currentTimer);
    this.highlightTimers.set(id, setTimeout(() => {
      this.highlightTimers.delete(id);
      this.highlightedIds.update((ids) => {
        const nextIds = new Set(ids);
        nextIds.delete(id);
        return nextIds;
      });
    }, 1800));
  }

  private playNotificationSound(): void {
    try {
      this.audioContext ??= new AudioContext();
      const context = this.audioContext;
      const play = () => {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, context.currentTime);
        oscillator.frequency.exponentialRampToValueAtTime(660, context.currentTime + 0.16);
        gain.gain.setValueAtTime(0.0001, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.16, context.currentTime + 0.015);
        gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.2);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.21);
      };
      if (context.state === 'suspended') {
        void context.resume().then(play).catch(() => undefined);
      } else {
        play();
      }
    } catch {
      // Browsers may block audio until the first user interaction.
    }
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
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    for (const timer of this.highlightTimers.values()) clearTimeout(timer);
    document.removeEventListener('pointerdown', this.unlockNotificationAudio);
    document.removeEventListener('keydown', this.unlockNotificationAudio);
    void this.audioContext?.close();
    this.wsSub?.unsubscribe();
  }
}
