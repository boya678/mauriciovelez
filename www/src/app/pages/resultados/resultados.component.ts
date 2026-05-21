import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { catchError, of, switchMap, tap } from 'rxjs';

import { LoteriasService, LoteriaResultado } from '../../core/services/loterias.service';

type LoadState = 'loading' | 'ok' | 'error';

@Component({
  selector: 'app-resultados',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe],
  templateUrl: './resultados.component.html',
  styleUrl: './resultados.component.scss',
})
export class ResultadosComponent {
  private readonly loterias = inject(LoteriasService);

  /** Fecha en formato yyyy-mm-dd (input type=date) */
  readonly fecha = signal<string>(this.todayStr());
  readonly q = signal('');
  readonly state = signal<LoadState>('loading');
  readonly errorMsg = signal<string>('');

  /** Resultados crudos del backend para la fecha seleccionada */
  readonly resultados = toSignal(
    toObservable(this.fecha).pipe(
      tap(() => { this.state.set('loading'); this.errorMsg.set(''); }),
      switchMap((f) =>
        this.loterias.getResultados(f).pipe(
          tap(() => this.state.set('ok')),
          catchError((err) => {
            this.state.set('error');
            this.errorMsg.set(
              err?.status === 0
                ? 'No se pudo conectar con el servidor.'
                : `Error ${err?.status ?? ''} ${err?.statusText ?? ''}`.trim(),
            );
            return of<LoteriaResultado[]>([]);
          }),
        ),
      ),
    ),
    { initialValue: [] as LoteriaResultado[] },
  );

  readonly filtrados = computed(() => {
    const term = this.q().trim().toLowerCase();
    const list = this.resultados();
    if (!term) return list;
    return list.filter(
      (l) =>
        l.loteria.toLowerCase().includes(term) ||
        l.resultado.toLowerCase().includes(term) ||
        (l.serie ?? '').toLowerCase().includes(term) ||
        (l.slug ?? '').toLowerCase().includes(term),
    );
  });

  readonly esHoy = computed(() => this.fecha() === this.todayStr());

  hoy()  { this.fecha.set(this.todayStr()); }
  ayer() {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    this.fecha.set(this.toStr(d));
  }
  reintentar() {
    // Forzar re-emisión asignando el mismo valor con un nuevo string
    const f = this.fecha();
    this.fecha.set('');
    queueMicrotask(() => this.fecha.set(f));
  }
  clearQ() { this.q.set(''); }

  private todayStr(): string { return this.toStr(new Date()); }
  private toStr(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
  }
}
