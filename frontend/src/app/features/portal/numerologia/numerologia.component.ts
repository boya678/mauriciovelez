import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../../core/services/auth.service';

interface NumeroCard {
  titulo: string;
  numero: number | string;
  descripcion: string;
  icono: string;
  color: 'gold' | 'purple' | 'red' | 'cyan' | 'green';
}

@Component({
  selector: 'app-numerologia',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './numerologia.component.html',
  styleUrl: './numerologia.component.scss',
})
export class NumerologiaComponent {
  clienteNombre: string;

  semanaNumeros = [3, 7, 14, 22, 31, 42];

  cards: NumeroCard[] = [
    {
      titulo: 'Número de Vida',
      numero: 7,
      descripcion:
        'El buscador de la verdad. Analítico, introspectivo y espiritualmente orientado. Tu camino está marcado por la sabiduría interior.',
      icono: '✦',
      color: 'purple',
    },
    {
      titulo: 'Número del Destino',
      numero: 3,
      descripcion:
        'El comunicador creativo. Expresas ideas con originalidad y atraes abundancia a través de tu creatividad y optimismo genuino.',
      icono: '★',
      color: 'gold',
    },
    {
      titulo: 'Número de la Suerte',
      numero: 9,
      descripcion:
        'Número de completitud y fortuna. Grandes oportunidades surgen cuando los ciclos llegan a su plenitud.',
      icono: '♦',
      color: 'red',
    },
    {
      titulo: 'Número del Alma',
      numero: 5,
      descripcion:
        'Espíritu libre. Buscas libertad y experiencias nuevas. Los cambios son tus aliados y la aventura tu motor.',
      icono: '♠',
      color: 'cyan',
    },
    {
      titulo: 'Año Personal',
      numero: 2,
      descripcion:
        'Año de cooperación y relaciones. Es el momento para sembrar alianzas y confiar en los procesos que ya iniciaste.',
      icono: '⬡',
      color: 'green',
    },
    {
      titulo: 'Número Maestro',
      numero: 11,
      descripcion:
        'Eres un faro de inspiración para quienes te rodean. Tu intuición y sensibilidad son dones extraordinarios.',
      icono: '∞',
      color: 'gold',
    },
  ];

  constructor(private authService: AuthService) {
    this.clienteNombre = authService.getCliente()?.nombre ?? 'Visitante';
  }
}
