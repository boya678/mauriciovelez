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
      { path: '', redirectTo: 'numerologia', pathMatch: 'full' },
      {
        path: 'numerologia',
        loadComponent: () =>
          import('./features/portal/numerologia/numerologia.component').then(
            m => m.NumerologiaComponent
          ),
      },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
