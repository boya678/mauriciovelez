import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./layout/shell.component').then((m) => m.ShellComponent),
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./pages/home/home.component').then((m) => m.HomeComponent),
        title: 'Mauricio Vélez · Numerólogo — +20 años de Certeza, no Suerte',
      },
      {
        path: 'resultados',
        loadComponent: () =>
          import('./pages/resultados/resultados.component').then((m) => m.ResultadosComponent),
        title: 'Resultados Oficiales — Loterías y Chances de Colombia | Mauricio Vélez',
      },
      // Compatibilidad con URLs anteriores
      { path: 'loterias', redirectTo: 'resultados', pathMatch: 'full' },
      { path: 'chances',  redirectTo: 'resultados', pathMatch: 'full' },
      {
        path: 'metodo-numerologico',
        loadComponent: () =>
          import('./pages/estadisticas/estadisticas.component').then((m) => m.EstadisticasComponent),
        title: 'Método Numerológico — Estadística, Matemática y Tendencia Numérica | Mauricio Vélez',
      },
      {
        path: 'estudios-numerologicos',
        loadComponent: () =>
          import('./pages/analisis/analisis.component').then((m) => m.AnalisisComponent),
        title: 'Estudios Numerológicos — Análisis de Loterías y Chances | Mauricio Vélez',
      },
      // Compatibilidad con URLs anteriores
      { path: 'estadisticas', redirectTo: 'metodo-numerologico',    pathMatch: 'full' },
      { path: 'analisis',     redirectTo: 'estudios-numerologicos', pathMatch: 'full' },
      {
        path: 'politica-de-privacidad',
        loadComponent: () =>
          import('./pages/privacidad/privacidad.component').then((m) => m.PrivacidadComponent),
        title: 'Política de Privacidad — Mauricio Vélez Numerólogo',
      },
      {
        path: 'terminos-y-condiciones',
        loadComponent: () =>
          import('./pages/terminos/terminos.component').then((m) => m.TerminosComponent),
        title: 'Términos y Condiciones — Mauricio Vélez Numerólogo',
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
