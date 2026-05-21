import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { LiveService } from '../../core/services/live.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterLink, DatePipe],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent implements OnInit {
  readonly live = inject(LiveService);

  readonly whatsappNumber = '3225556333';
  readonly whatsappUrl =
    'https://wa.me/57' + this.whatsappNumber +
    '?text=' + encodeURIComponent('Hola Mauricio, vengo del portal y me interesa tu método.');
  readonly softwareUrl = 'https://portal.mauricioveleznumerologo.com/';
  readonly softwareName = 'Software Numerológico';

  readonly pilares = [
    { icon: 'analytics',     titulo: 'Estadística',         desc: 'Frecuencias, distribuciones y comportamiento histórico de los resultados oficiales.' },
    { icon: 'functions',     titulo: 'Matemática',          desc: 'Patrones numéricos, relaciones, sumas y secuencias verificables.' },
    { icon: 'trending_up',   titulo: 'Tendencia Numérica',  desc: 'Lectura del momento de cada número: ciclos, rachas y cambios de comportamiento.' },
  ];

  readonly hora = signal(new Date());
  readonly horaFmt = computed(() =>
    this.hora().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  );
  readonly fechaFmt = computed(() =>
    this.hora().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' })
  );

  ngOnInit(): void {
    this.live.start();
    setInterval(() => this.hora.set(new Date()), 1000);
  }
}
