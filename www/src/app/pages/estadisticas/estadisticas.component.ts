import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-estadisticas',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './estadisticas.component.html',
  styleUrl: './estadisticas.component.scss',
})
export class EstadisticasComponent {
  readonly whatsappUrl =
    'https://wa.me/573225556333?text=' +
    encodeURIComponent('Hola Mauricio, vengo de la página de tu método numerológico.');
  readonly softwareUrl = 'https://portal.mauricioveleznumerologo.com/';
  readonly softwareName = 'Software Numerológico';

  readonly pilares = [
    {
      n: '01',
      icon: 'analytics',
      titulo: 'Estadística histórica',
      bullets: [
        'Frecuencias y distribución real de los números en resultados oficiales.',
        'Números calientes, fríos y de rotación normal por lotería.',
        'Comportamiento por día de la semana, mes y temporada.',
      ],
      desc: 'Toda decisión parte de un dato verificable. Trabajo siempre sobre resultados oficiales, nunca sobre suposiciones.',
    },
    {
      n: '02',
      icon: 'functions',
      titulo: 'Patrones matemáticos',
      bullets: [
        'Relaciones entre cifras, sumas y secuencias.',
        'Combinaciones y descomposiciones recurrentes.',
        'Validación matemática de cada hipótesis antes de aplicarla.',
      ],
      desc: 'La matemática es el filtro que separa la intuición de la lectura seria. Si no se puede demostrar, no entra al método.',
    },
    {
      n: '03',
      icon: 'trending_up',
      titulo: 'Tendencia numérica',
      bullets: [
        'Lectura del momento de cada número: rachas, ciclos y descansos.',
        'Cambios de comportamiento por lotería y por chance.',
        'Identificación de números en transición.',
      ],
      desc: 'La parte que solo se construye con años. Más de 20 años leyendo el comportamiento del número me permiten entender cuándo un número entra, vive o se retira.',
    },
  ];

  readonly principios = [
    { icon: 'verified',    titulo: 'Datos oficiales',         desc: 'Siempre trabajo con resultados verificables.' },
    { icon: 'gavel',       titulo: 'Sin promesas falsas',     desc: 'No vendo aciertos. Entrego método y criterio.' },
    { icon: 'school',      titulo: 'Más de 20 años',          desc: 'Experiencia construida loto a loto, chance a chance.' },
    { icon: 'workspaces',  titulo: 'Aplicación práctica',     desc: 'El método se ejecuta en el Software Numerológico. Primera victoria gratis.' },
  ];
}
