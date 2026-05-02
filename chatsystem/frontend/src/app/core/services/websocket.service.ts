import { Injectable, OnDestroy } from '@angular/core';
import { Subject } from 'rxjs';
import { AuthService } from './auth.service';
import { environment } from '../../../environments/environment';

export interface WsEvent {
  type: 'new_message' | 'conversation_assigned' | 'conversation_closed' | 'pong' | string;
  conversation_id?: string;
  [key: string]: unknown;
}

@Injectable({ providedIn: 'root' })
export class WebSocketService implements OnDestroy {
  private ws: WebSocket | null = null;
  private readonly eventsSubject = new Subject<WsEvent>();
  readonly events$ = this.eventsSubject.asObservable();

  private readonly connectedSubject = new Subject<void>();
  readonly connected$ = this.connectedSubject.asObservable();

  private heartbeatRef?: ReturnType<typeof setInterval>;
  private reconnectRef?: ReturnType<typeof setTimeout>;
  private intentionalClose = false;

  constructor(private auth: AuthService) {}

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    const token = this.auth.getToken();
    const tenantSlug = this.auth.getTenantSlug();
    const agentId = this.auth.getAgentId();

    if (!token || !tenantSlug || !agentId) return;

    this.intentionalClose = false;
    const url = `${environment.wsUrl}/ws/${tenantSlug}/${agentId}?token=${token}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.startHeartbeat();
      this.connectedSubject.next();
    };

    this.ws.onmessage = ({ data }) => {
      try {
        const event: WsEvent = JSON.parse(data as string);
        this.eventsSubject.next(event);
      } catch {
        // ignore malformed frames
      }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      if (!this.intentionalClose) {
        this.reconnectRef = setTimeout(() => this.connect(), 3000);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.stopHeartbeat();
    clearTimeout(this.reconnectRef);
    this.ws?.close();
    this.ws = null;
  }

  send(data: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private startHeartbeat(): void {
    this.heartbeatRef = setInterval(() => this.send({ type: 'ping' }), 10_000);
  }

  private stopHeartbeat(): void {
    clearInterval(this.heartbeatRef);
  }

  ngOnDestroy(): void {
    this.disconnect();
    this.eventsSubject.complete();
    this.connectedSubject.complete();
  }
}
