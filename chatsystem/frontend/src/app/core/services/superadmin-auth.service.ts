import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { SuperadminTokenOut, SuperadminUser } from '../models/superadmin.model';

@Injectable({ providedIn: 'root' })
export class SuperadminAuthService {
  private readonly TOKEN_KEY = 'sa_token';

  isLoggedIn = signal(this.hasValidToken());

  constructor(private http: HttpClient, private router: Router) {}

  login(email: string, password: string) {
    return this.http
      .post<SuperadminTokenOut>(
        `${environment.apiUrl}/api/v1/superadmin/login`,
        { email, password }
      )
      .pipe(
        tap(res => {
          localStorage.setItem(this.TOKEN_KEY, res.access_token);
          this.isLoggedIn.set(true);
        })
      );
  }

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    this.isLoggedIn.set(false);
    this.router.navigate(['/sa/login']);
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  getPayload(): Record<string, any> | null {
    const token = this.getToken();
    if (!token) return null;
    try {
      return JSON.parse(atob(token.split('.')[1]));
    } catch {
      return null;
    }
  }

  getName(): string {
    return this.getPayload()?.['name'] ?? 'Superadmin';
  }

  private hasValidToken(): boolean {
    const token = this.getToken();
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload['role'] === 'superadmin' && payload['exp'] * 1000 > Date.now();
    } catch {
      return false;
    }
  }
}
