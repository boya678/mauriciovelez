import { Component, inject } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ResultadosService } from '../../core/services/resultados.service';

@Component({
  selector: 'app-analisis',
  standalone: true,
  imports: [CommonModule, DatePipe, RouterLink],
  templateUrl: './analisis.component.html',
  styleUrl: './analisis.component.scss',
})
export class AnalisisComponent {
  private resultados = inject(ResultadosService);

  readonly whatsappUrl =
    'https://wa.me/573225556333?text=' +
    encodeURIComponent('Hola Mauricio, vengo de tus estudios numerológicos.');
  readonly softwareUrl = 'https://portal.mauricioveleznumerologo.com/';
  readonly softwareName = 'Software Numerológico';

  readonly estudios = this.resultados.getAnalisis();
}
