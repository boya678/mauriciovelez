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
  actionError = signal<string | null>(null);
  sendError = signal<string | null>(null);
  newMessage = '';
  showReopenConfirm = signal(false);
  reopening = signal(false);
  recording = signal(false);
  mediaSending = signal(false);

  private shouldScroll = false;
  private wsSub?: Subscription;
  private mediaRecorder?: MediaRecorder;
  private mediaStream?: MediaStream;
  private recordedChunks: BlobPart[] = [];

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
        (
          ev.type === 'new_message' ||
          ev.type === 'conversation_waiting' ||
          ev.type === 'conversation_assigned' ||
          ev.type === 'conversation_closed'
        ) &&
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
    this.actionError.set(null);
    this.conversationsService.take(id).subscribe({
      next: () => this.load(id),
      error: (err) => this.actionError.set(
        err?.error?.detail || 'No se pudo asignar la conversación.'
      ),
    });
  }

  close(): void {
    const id = this.conversation()?.id;
    if (!id) return;
    this.actionError.set(null);
    this.conversationsService.close(id).subscribe({
      next: () => this.load(id),
      error: (err) => this.actionError.set(
        err?.error?.detail || 'No se pudo cerrar la conversación.'
      ),
    });
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

  onImageSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const id = this.conversation()?.id;
    const file = input.files?.[0];
    if (!id || !file || this.mediaSending()) return;

    this.mediaSending.set(true);
    this.sendError.set(null);
    this.conversationsService.sendMedia(id, file, file.name, '').subscribe({
      next: () => {
        this.mediaSending.set(false);
        this.load(id);
        input.value = '';
      },
      error: (err) => {
        this.mediaSending.set(false);
        const detail = err?.error?.detail;
        this.sendError.set(
          typeof detail === 'string' ? detail : 'Error al enviar la imagen. Intenta de nuevo.'
        );
        input.value = '';
      },
    });
  }

  async startRecording(): Promise<void> {
    const id = this.conversation()?.id;
    if (!id || this.recording() || this.mediaSending()) return;

    try {
      this.sendError.set(null);
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const supportedMime = this.getPreferredAudioMimeType();
      this.recordedChunks = [];
      this.mediaRecorder = supportedMime
        ? new MediaRecorder(this.mediaStream, { mimeType: supportedMime })
        : new MediaRecorder(this.mediaStream);

      this.mediaRecorder.ondataavailable = (ev: BlobEvent) => {
        if (ev.data && ev.data.size > 0) this.recordedChunks.push(ev.data);
      };
      this.mediaRecorder.onstop = () => {
        void this.sendRecordedAudio();
      };

      this.mediaRecorder.start();
      this.recording.set(true);
    } catch (err) {
      this.cleanupRecorder();
      this.sendError.set('No se pudo acceder al micrófono. Revisa permisos del navegador.');
    }
  }

  stopRecording(): void {
    if (!this.mediaRecorder || !this.recording()) return;
    this.recording.set(false);
    if (this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
  }

  private async sendRecordedAudio(): Promise<void> {
    const id = this.conversation()?.id;
    if (!id) {
      this.cleanupRecorder();
      return;
    }

    const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
    const ext = this.extensionForMime(mimeType);
    const blob = new Blob(this.recordedChunks, { type: mimeType });
    this.recordedChunks = [];

    if (!blob.size) {
      this.cleanupRecorder();
      this.sendError.set('No se capturó audio. Intenta grabar de nuevo.');
      return;
    }

    this.mediaSending.set(true);
    this.conversationsService.sendMedia(id, blob, `voice_note.${ext}`, '').subscribe({
      next: () => {
        this.mediaSending.set(false);
        this.cleanupRecorder();
        this.load(id);
      },
      error: (err) => {
        this.mediaSending.set(false);
        this.cleanupRecorder();
        const detail = err?.error?.detail;
        this.sendError.set(
          typeof detail === 'string' ? detail : 'Error al enviar el audio. Intenta de nuevo.'
        );
      },
    });
  }

  private getPreferredAudioMimeType(): string {
    const candidates = ['audio/ogg;codecs=opus', 'audio/webm;codecs=opus', 'audio/mp4'];
    for (const mime of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) {
        return mime;
      }
    }
    return '';
  }

  private extensionForMime(mimeType: string): string {
    if (mimeType.includes('ogg')) return 'ogg';
    if (mimeType.includes('mp4')) return 'mp4';
    if (mimeType.includes('mpeg')) return 'mp3';
    return 'webm';
  }

  private cleanupRecorder(): void {
    try {
      this.mediaStream?.getTracks().forEach((t) => t.stop());
    } catch {
      // ignore cleanup errors
    }
    this.mediaStream = undefined;
    this.mediaRecorder = undefined;
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
    const s = this.conversation()?.status;
    return s === 'waiting_human' || s === 'bot_active';
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

  pedirContacto(): void {
    const id = this.conversationId();
    if (!id) return;
    this.conversationsService.pedirContacto(id).subscribe({
      next: () => alert('Solicitud de contacto enviada.'),
      error: (err) => alert('Error al enviar solicitud: ' + (err?.error?.detail ?? err.message)),
    });
  }

  /** Returns true when the conversation phone is still a BSUID (contains ".") */
  isBsuid(): boolean {
    return (this.conversation()?.phone ?? '').includes('.');
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
    const d = new Date(iso);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
    const isYesterday = d.toDateString() === yesterday.toDateString();
    const time = d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
    if (isToday) return time;
    if (isYesterday) return `ayer ${time}`;
    return d.toLocaleDateString('es', { day: 'numeric', month: 'short' }) + ' ' + time;
  }

  formatDateSeparator(iso: string): string {
    const d = new Date(iso);
    const now = new Date();
    const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === now.toDateString()) return 'Hoy';
    if (d.toDateString() === yesterday.toDateString()) return 'Ayer';
    return d.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
  }

  showDateSeparator(msgs: any[], index: number): boolean {
    if (index === 0) return true;
    const prev = new Date(msgs[index - 1].created_at).toDateString();
    const curr = new Date(msgs[index].created_at).toDateString();
    return prev !== curr;
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
    this.cleanupRecorder();
    this.wsSub?.unsubscribe();
  }
}
