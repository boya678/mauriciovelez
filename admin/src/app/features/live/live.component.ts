import {
  Component,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { environment } from '../../../environments/environment';

export interface LiveEvent {
  id: number;
  tipo: 'ganador' | 'nuevo_cliente' | 'nuevo_vip';
  nombre: string;
  // ganador only
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

@Component({
  selector: 'app-live',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './live.component.html',
  styleUrl: './live.component.scss',
})
export class LiveComponent implements OnInit, OnDestroy {
  events = signal<LiveEvent[]>([]);
  muted = signal(false);
  connected = signal(false);

  private ws: WebSocket | null = null;
  private counter = 0;
  private readonly MAX_EVENTS = 100;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;

  ngOnInit(): void {
    this.connect();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.reconnectTimer && clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }

  private connect(): void {
    this.ws?.close();

    // Convertir http(s) → ws(s) sobre la misma base URL
    const apiUrl = environment.apiUrl.replace(/^http/, 'ws');
    const url = `${apiUrl}/admin/live/ws`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.connected.set(true);
      this.reconnectTimer && clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
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

    this.ws.onerror = () => {
      // onclose se disparará después y manejará la reconexión
      this.connected.set(false);
    };

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

        const isHistorical = Date.now() - tsMs > 5000;

        this.events.update((list) => {
          const next = [event, ...list];
          return next.length > this.MAX_EVENTS ? next.slice(0, this.MAX_EVENTS) : next;
        });

        if (!this.muted() && !isHistorical) {
          this.playSound(raw.tipo);
        }
      } catch {
        // ignore malformed events
      }
    };
  }

  toggleMute(): void {
    this.muted.update((v) => !v);
  }

  private playSound(tipo: string): void {
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (tipo === 'ganador') {
        // Chord: C5 + E5
        osc.frequency.value = 523.25;
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
      } else if (tipo === 'nuevo_vip') {
        osc.frequency.value = 659.25;
        gain.gain.setValueAtTime(0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      } else {
        osc.frequency.value = 440;
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      }

      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.6);
    } catch {
      // AudioContext not supported
    }
  }
}
