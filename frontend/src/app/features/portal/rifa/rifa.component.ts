import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RifasService, RifaPublic, Boleta } from '../../../core/services/rifas.service';

@Component({
  selector: 'app-rifa',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './rifa.component.html',
  styleUrl: './rifa.component.scss',
})
export class RifaComponent implements OnInit {
  tab = signal<'activa' | 'historico'>('activa');

  // Rifa activa
  rifaActiva = signal<RifaPublic | null>(null);
  misBoletasActiva = signal<Boleta[]>([]);
  loadingActiva = signal(true);

  // Histórico
  historico = signal<RifaPublic[]>([]);
  loadingHistorico = signal(false);
  boletasHistorico = new Map<string, Boleta[]>();
  expandedId = signal<string | null>(null);

  constructor(private svc: RifasService) {}

  ngOnInit() {
    this.cargarActiva();
  }

  setTab(t: 'activa' | 'historico') {
    this.tab.set(t);
    if (t === 'historico' && this.historico().length === 0) {
      this.cargarHistorico();
    }
  }

  cargarActiva() {
    this.loadingActiva.set(true);
    this.svc.getActiva().subscribe({
      next: rifa => {
        this.rifaActiva.set(rifa);
        this.loadingActiva.set(false);
        if (rifa) {
          this.svc.getMisBoletas().subscribe({ next: b => this.misBoletasActiva.set(b) });
        }
      },
      error: () => this.loadingActiva.set(false),
    });
  }

  cargarHistorico() {
    this.loadingHistorico.set(true);
    this.svc.getHistorico().subscribe({
      next: rifas => { this.historico.set(rifas); this.loadingHistorico.set(false); },
      error: () => this.loadingHistorico.set(false),
    });
  }

  toggleHistorico(rifa: RifaPublic) {
    if (this.expandedId() === rifa.id) {
      this.expandedId.set(null);
      return;
    }
    this.expandedId.set(rifa.id);
    if (!this.boletasHistorico.has(rifa.id)) {
      this.svc.getMisBoletasHistorico(rifa.id).subscribe({
        next: b => { this.boletasHistorico.set(rifa.id, b); },
      });
    }
  }

  getMisBoletasHist(rifaId: string): Boleta[] {
    return this.boletasHistorico.get(rifaId) ?? [];
  }

  imagenUrl(id: string): string { return this.svc.imagenUrl(id); }

  formatNum(n: number, max: number): string {
    return String(n).padStart(String(max).length, '0');
  }

  yoGane(boletas: Boleta[]): boolean {
    return boletas.some(b => b.es_ganadora);
  }
}
