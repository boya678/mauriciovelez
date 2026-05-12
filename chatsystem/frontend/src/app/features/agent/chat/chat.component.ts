import {
  AfterViewChecked,
  Component,
  ElementRef,
  EventEmitter,
  input,
  OnDestroy,
  OnInit,
  output,
  signal,
  ViewChild,
  effect,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { ConversationsService } from '../../../core/services/conversations.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { AuthService } from '../../../core/services/auth.service';
import { ConversationDetail } from '../../../core/models/conversation.model';
import { Message } from '../../../core/models/message.model';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  conversationId = input.required<string>();
  conversationReopened = output<void>();

  conversation = signal<ConversationDetail | null>(null);
  loading = signal(false);
  sending = signal(false);
  loadError = signal<string | null>(null);
  sendError = signal<string | null>(null);
  newMessage = '';
  showReopenConfirm = signal(false);
  reopening = signal(false);

  private shouldScroll = false;
  private wsSub?: Subscription;

  @ViewChild('msgContainer') msgContainer!: ElementRef<HTMLDivElement>;

  constructor(
    private conversationsService: ConversationsService,
    private ws: WebSocketService,
    private auth: AuthService
  ) {
    // Reload when conversationId changes
    effect(() => {
      const id = this.conversationId();
      if (id) this.load(id);
    }, { allowSignalWrites: true });
  }

  ngOnInit(): void {
    this.wsSub = this.ws.events$.subscribe((ev) => {
      const id = this.conversation()?.id;
      if (
        (ev.type === 'new_message' || ev.type === 'conversation_assigned' || ev.type === 'conversation_closed') &&
        ev['conversation_id'] === id
      ) {
        this.load(id!);
      }
    });
  }

  private load(id: string): void {
    this.loading.set(true);
    this.loadError.set(null);
    console.log('[chat] loading conversation', id);
    this.conversationsService.getConversation(id).subscribe({
      next: (detail) => {
        console.log('[chat] loaded', detail);
        this.conversation.set(detail);
        this.loading.set(false);
        this.shouldScroll = true;
      },
      error: (err) => {
        console.error('[chat] load error', err);
        this.loadError.set(err?.error?.detail || err?.message || 'Error al cargar conversación');
        this.loading.set(false);
      },
    });
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
    }
  }

  private scrollToBottom(): void {
    const el = this.msgContainer?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }

  take(): void {
    const id = this.conversation()?.id;
    if (!id) return;
    this.conversationsService.take(id).subscribe(() => this.load(id));
  }

  close(): void {
    const id = this.conversation()?.id;
    if (!id) return;
    this.conversationsService.close(id).subscribe(() => this.load(id));
  }

  send(): void {
    const content = this.newMessage.trim();
    const id = this.conversation()?.id;
    if (!content || !id || this.sending()) return;

    this.sending.set(true);
    this.sendError.set(null);
    this.conversationsService.sendMessage(id, content).subscribe({
      next: () => {
        this.newMessage = '';
        this.sending.set(false);
        this.load(id);
      },
      error: (err) => {
        this.sending.set(false);
        const detail = err?.error?.detail;
        this.sendError.set(
          typeof detail === 'string' ? detail : 'Error al enviar el mensaje. Intenta de nuevo.'
        );
      },
    });
  }

  onEnter(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  get myAgentId(): string {
    return this.auth.getAgentId();
  }

  get isAssignedToMe(): boolean {
    return this.conversation()?.assigned_agent_id === this.myAgentId;
  }

  get canTake(): boolean {
    return this.conversation()?.status === 'waiting_human';
  }

  get canSend(): boolean {
    return this.conversation()?.status === 'human_active' && this.isAssignedToMe;
  }

  get canClose(): boolean {
    return this.conversation()?.status === 'human_active' && this.isAssignedToMe;
  }

  get isClosed(): boolean {
    return this.conversation()?.status === 'closed';
  }

  get windowOpen(): boolean {
    return this.conversation()?.window_open ?? true;
  }

  windowTimeLeft(): string {
    const ts = this.conversation()?.last_user_message_at;
    if (!ts) return '';
    const remainingMs = 24 * 3600 * 1000 - (Date.now() - new Date(ts).getTime());
    if (remainingMs <= 0) return '';
    const h = Math.floor(remainingMs / 3600000);
    const m = Math.floor((remainingMs % 3600000) / 60000);
    return h > 0 ? `${h} h ${m} min restantes` : `${m} min restantes`;
  }

  reopen(): void {
    const id = this.conversation()?.id;
    if (!id) return;
    this.reopening.set(true);
    this.conversationsService.reopen(id).subscribe({
      next: () => {
        this.reopening.set(false);
        this.showReopenConfirm.set(false);
        this.load(id);
        this.conversationReopened.emit();
      },
      error: () => this.reopening.set(false),
    });
  }

  bubbleClass(msg: Message): string {
    if (msg.sender_type === 'user') return 'bubble bubble-user';
    if (msg.sender_type === 'bot') return 'bubble bubble-bot';
    return 'bubble bubble-human';
  }

  senderLabel(msg: Message): string {
    if (msg.sender_type === 'user') return 'Cliente';
    if (msg.sender_type === 'bot') return 'Bot';
    return 'Agente';
  }

  formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  }

  parseInteractive(content: string): any | null {
    if (!content || !content.trim().startsWith('{')) return null;
    try {
      const parsed = JSON.parse(content);
      if (parsed.menu_type === 'buttons' || parsed.menu_type === 'list') return parsed;
    } catch { /* not JSON */ }
    return null;
  }

  openImg(event: MouseEvent): void {
    const img = event.target as HTMLImageElement;
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;z-index:9999;cursor:zoom-out';
    const clone = document.createElement('img');
    clone.src = img.src;
    clone.style.cssText = 'max-width:90vw;max-height:90vh;border-radius:8px;box-shadow:0 4px 32px #0008';
    overlay.appendChild(clone);
    overlay.addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
  }

  ngOnDestroy(): void {
    this.wsSub?.unsubscribe();
  }
}
