import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LoteriasService, ResultadoLoteria } from '../../core/services/loterias.service';
import { todayCol } from '../../core/utils/col-date';

function today(): string {
  return todayCol();
}

@Component({
  selector: 'app-loterias',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './loterias.component.html',
  styleUrl: './loterias.component.scss',
})
export class LoteriasComponent implements OnInit {
  resultados = signal<ResultadoLoteria[]>([]);
  loading = signal(false);
  errorMsg = signal('');

  fecha = today();

  constructor(private svc: LoteriasService) {}

  ngOnInit() { this.load(); }

  load() {
    this.loading.set(true);
    this.errorMsg.set('');
    this.svc.getResultados(this.fecha).subscribe({
      next: data => { this.resultados.set(data); this.loading.set(false); },
      error: () => { this.errorMsg.set('Error al cargar resultados'); this.loading.set(false); },
    });
  }

  get totalAciertos(): number {
    return this.resultados().reduce((s, r) => s + r.total_aciertos, 0);
  }
}
