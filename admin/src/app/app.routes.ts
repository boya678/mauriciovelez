import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: '/login', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login.component').then(m => m.LoginComponent),
  },
  {
    path: 'admin',
    loadComponent: () => import('./features/layout/layout.component').then(m => m.LayoutComponent),
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'clientes', pathMatch: 'full' },
      {
        path: 'clientes',
        loadComponent: () => import('./features/clientes/clientes.component').then(m => m.ClientesComponent),
      },
      {
        path: 'usuarios',
        loadComponent: () => import('./features/usuarios/usuarios.component').then(m => m.UsuariosComponent),
      },
      {
        path: 'audit',
        loadComponent: () => import('./features/audit/audit.component').then(m => m.AuditComponent),
      },
      {
        path: 'historico',
        loadComponent: () => import('./features/historico/historico.component').then(m => m.HistoricoComponent),
      },
    ],
  },
  { path: '**', redirectTo: '/login' },
];
