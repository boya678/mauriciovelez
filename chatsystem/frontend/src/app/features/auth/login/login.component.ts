import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  email = '';
  password = '';
  tenantSlug = '';
  loading = signal(false);
  error = signal('');

  constructor(private auth: AuthService, private router: Router) {}

  submit() {
    if (!this.email || !this.password || !this.tenantSlug) {
      this.error.set('Completa todos los campos.');
      return;
    }

    this.loading.set(true);
    this.error.set('');

    this.auth.login(this.email, this.password, this.tenantSlug).subscribe({
      next: () => this.router.navigate(['/inbox']),
      error: (err) => {
        this.loading.set(false);
        this.error.set(
          err?.error?.detail ?? 'Credenciales incorrectas. Intenta de nuevo.'
        );
      },
    });
  }
}
