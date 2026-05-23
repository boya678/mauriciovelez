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
      // Compatibilidad con URLs anteriores
      { path: 'resultados',             redirectTo: '', pathMatch: 'full' },
      { path: 'loterias',               redirectTo: '', pathMatch: 'full' },
      { path: 'chances',                redirectTo: '', pathMatch: 'full' },
      { path: 'estadisticas',           redirectTo: '', pathMatch: 'full' },
      { path: 'analisis',               redirectTo: '', pathMatch: 'full' },
      { path: 'metodo-numerologico',    redirectTo: '', pathMatch: 'full' },
      { path: 'estudios-numerologicos', redirectTo: '', pathMatch: 'full' },
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
