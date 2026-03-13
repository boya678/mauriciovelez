import { Component } from '@angular/core';
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
  usuario = '';
  clave = '';
  error = '';
  loading = false;

  constructor(private auth: AuthService, private router: Router) {
    if (this.auth.isAuthenticated()) this.router.navigate(['/admin']);
  }

  submit() {
    if (!this.usuario || !this.clave) return;
    this.loading = true;
    this.error = '';
    this.auth.login(this.usuario, this.clave).subscribe({
      next: () => this.router.navigate(['/admin']),
      error: () => {
        this.error = 'Credenciales incorrectas';
        this.loading = false;
      },
    });
  }
}
