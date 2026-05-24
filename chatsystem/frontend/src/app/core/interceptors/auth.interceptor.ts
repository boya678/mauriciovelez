import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  // Skip if request already carries its own Authorization (e.g. superadmin requests)
  if (req.headers.has('Authorization')) return next(req);

  const auth = inject(AuthService);
  const token = auth.getToken();
  const tenantSlug = auth.getTenantSlug();

  // Skip if no agent token
  if (!token) return next(req);

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
  if (tenantSlug) headers['X-Tenant-ID'] = tenantSlug;

  return next(req.clone({ setHeaders: headers }));
};
