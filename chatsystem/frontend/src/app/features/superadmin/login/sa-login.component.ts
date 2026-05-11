import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SuperadminAuthService } from '../../../core/services/superadmin-auth.service';

@Component({
  selector: 'app-sa-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sa-login.component.html',
  styleUrl: './sa-login.component.scss',
})
export class SaLoginComponent {
  email = '';
  password = '';
  loading = signal(false);
  error = signal('');

  constructor(private auth: SuperadminAuthService, private router: Router) {}

  submit(): void {
    if (!this.email || !this.password) {
      this.error.set('Email y contraseña son requeridos.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.auth.login(this.email, this.password).subscribe({
      next: () => this.router.navigate(['/sa']),
      error: () => {
        this.error.set('Credenciales inválidas.');
        this.loading.set(false);
      },
    });
  }
}
