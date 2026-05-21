import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login/login.component').then(m => m.LoginComponent),
  },
  {
    path: 'portal',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/portal/layout/portal-layout.component').then(
        m => m.PortalLayoutComponent
      ),
    children: [
      { path: '', redirectTo: 'referidos', pathMatch: 'full' },
      {
        path: 'referidos',
        loadComponent: () =>
          import('./features/portal/referidos/referidos.component').then(
            m => m.ReferidosComponent
          ),
      },
      {
        path: 'mis-datos',
        loadComponent: () =>
          import('./features/portal/mis-datos/mis-datos.component').then(
            m => m.MisDatosComponent
          ),
      },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
