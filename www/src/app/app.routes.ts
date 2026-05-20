import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./pages/home/home.component').then((m) => m.HomeComponent),
  },
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
  { path: '**', redirectTo: '' },
];
