import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SuperadminAuthService } from '../services/superadmin-auth.service';

export const saAuthGuard: CanActivateFn = () => {
  const auth = inject(SuperadminAuthService);
  const router = inject(Router);
  if (auth.isLoggedIn()) return true;
  return router.createUrlTree(['/sa/login']);
};
