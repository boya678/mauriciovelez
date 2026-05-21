import { Injectable, OnDestroy, signal } from '@angular/core';
import { environment } from '../../../environments/environment';

export interface LiveEvent {
  id: number;
  tipo: 'ganador' | 'nuevo_cliente' | 'nuevo_vip';
  nombre: string;
  numero?: string;
  loteria?: string;
  tipo_acierto?: string;
  veces_gano?: number;
  timestamp: Date;
}

const TIPO_LABEL: Record<string, string> = {
  directo: 'Directo',
  directo_metodo: 'Directo Método',
  tres_directo: 'Tres Directo',
  tres_metodo: 'Tres Método',
};

@Injectable({ providedIn: 'root' })
export class LiveService implements OnDestroy {
  readonly events = signal<LiveEvent[]>([]);
  readonly connected = signal(false);

  private ws: WebSocket | null = null;
  private counter = 0;
  private readonly MAX_EVENTS = 80;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;
  private started = false;

  start(): void {
    if (this.started) return;
    this.started = true;
    this.connect();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }

  private connect(): void {
    this.ws?.close();
    const wsBase = environment.apiUrl.replace(/^http/, 'ws');
    this.ws = new WebSocket(`${wsBase}/admin/live/ws`);

    this.ws.onopen = () => {
      this.connected.set(true);
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.ws.onclose = () => {
      this.connected.set(false);
      if (this.destroyed) return;
      if (!this.reconnectTimer) {
        this.reconnectTimer = setTimeout(() => {
          this.reconnectTimer = null;
          this.connect();
        }, 3000);
      }
    };

    this.ws.onerror = () => this.connected.set(false);

    this.ws.onmessage = (ev) => {
      try {
        const raw = JSON.parse(ev.data);
        const tsMs = typeof raw.ts === 'number' ? raw.ts * 1000 : Date.now();
        const event: LiveEvent = {
          id: ++this.counter,
          tipo: raw.tipo,
          nombre: raw.nombre ?? '',
          numero: raw.numero,
          loteria: raw.loteria,
          tipo_acierto: raw.tipo_acierto
            ? TIPO_LABEL[raw.tipo_acierto] ?? raw.tipo_acierto
            : undefined,
          veces_gano: raw.veces_gano,
          timestamp: new Date(tsMs),
        };
        this.events.update((list) => {
          const next = [event, ...list];
          return next.length > this.MAX_EVENTS ? next.slice(0, this.MAX_EVENTS) : next;
        });
      } catch {
        /* ignore */
      }
    };
  }
}
