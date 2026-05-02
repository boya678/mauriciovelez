import {
  AfterViewChecked,
  Component,
  ElementRef,
  input,
  OnDestroy,
  OnInit,
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

  conversation = signal<ConversationDetail | null>(null);
  loading = signal(false);
  sending = signal(false);
  loadError = signal<string | null>(null);
  newMessage = '';

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
    this.conversationsService.sendMessage(id, content).subscribe({
      next: () => {
        this.newMessage = '';
        this.sending.set(false);
        this.load(id);
      },
      error: () => this.sending.set(false),
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

  ngOnDestroy(): void {
    this.wsSub?.unsubscribe();
  }
}
