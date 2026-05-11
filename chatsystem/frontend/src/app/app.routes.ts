import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { adminGuard } from './core/guards/admin.guard';
import { saAuthGuard } from './core/guards/sa-auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login/login.component').then(m => m.LoginComponent),
  },
  {
    path: '',
    loadComponent: () =>
      import('./features/layout/app-layout.component').then(m => m.AppLayoutComponent),
    canActivate: [authGuard],
    children: [
      {
        path: 'inbox',
        loadComponent: () =>
          import('./features/agent/inbox/inbox.component').then(m => m.InboxComponent),
      },
      {
        path: 'admin',
        canActivate: [adminGuard],
        children: [
          {
            path: 'dashboard',
            loadComponent: () =>
              import('./features/admin/dashboard/dashboard.component').then(m => m.DashboardComponent),
          },
          {
            path: 'agents',
            loadComponent: () =>
              import('./features/admin/agents/agents-mgmt.component').then(m => m.AgentsMgmtComponent),
          },
          {
            path: 'settings',
            loadComponent: () =>
              import('./features/admin/settings/settings.component').then(m => m.SettingsComponent),
          },
          {
            path: 'tools',
            loadComponent: () =>
              import('./features/admin/tools/tools.component').then(m => m.ToolsComponent),
          },
          { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
        ],
      },
      { path: '', redirectTo: 'inbox', pathMatch: 'full' },
    ],
  },
  {
    path: 'sa/login',
    loadComponent: () =>
      import('./features/superadmin/login/sa-login.component').then(m => m.SaLoginComponent),
  },
  {
    path: 'sa',
    loadComponent: () =>
      import('./features/superadmin/layout/sa-layout.component').then(m => m.SaLayoutComponent),
    canActivate: [saAuthGuard],
    children: [
      {
        path: 'tenants',
        loadComponent: () =>
          import('./features/superadmin/tenants/sa-tenants.component').then(m => m.SaTenantsComponent),
      },
      {
        path: 'users',
        loadComponent: () =>
          import('./features/superadmin/users/sa-users.component').then(m => m.SaUsersComponent),
      },
      { path: '', redirectTo: 'tenants', pathMatch: 'full' },
    ],
  },
  { path: '**', redirectTo: '' },
];
