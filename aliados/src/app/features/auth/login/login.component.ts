import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, CommonModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  celular = '';
  codigoVip = '';
  loading = signal(false);
  errorMsg = signal('');

  constructor(private auth: AuthService, private router: Router) {}

  submit(): void {
    this.errorMsg.set('');
    const cel = this.celular.trim();
    const cod = this.codigoVip.trim();
    if (!cel || !cod) {
      this.errorMsg.set('Ingresa tu celular y código de aliado');
      return;
    }
    this.loading.set(true);
    this.auth.login({ celular: cel, codigo_vip: cod }).subscribe({
      next: () => this.router.navigate(['/portal/referidos']),
      error: err => {
        this.errorMsg.set(err.error?.detail ?? 'Credenciales inválidas');
        this.loading.set(false);
      },
    });
  }
}
