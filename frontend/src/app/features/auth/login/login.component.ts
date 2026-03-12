import { Component, OnInit, signal } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../../core/services/auth.service';

interface Particle {
  symbol: string;
  left: string;
  size: string;
  duration: string;
  delay: string;
  opacity: string;
}

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, CommonModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent implements OnInit {
  form!: FormGroup;
  loading = signal(false);
  errorMsg = signal('');
  particles: Particle[] = [];

  private readonly symbols = ['♦', '★', '$', '✦', '♠', '♣', '♥', '7', '♞', '⬡'];

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    if (this.authService.isAuthenticated()) {
      this.router.navigate(['/portal']);
      return;
    }
    this.form = this.fb.group({
      nombre: ['', [Validators.required, Validators.minLength(2)]],
      celular: ['', [Validators.required, Validators.pattern(/^\d{7,15}$/)]],
    });
    this.buildParticles();
  }

  private buildParticles(): void {
    this.particles = Array.from({ length: 24 }, (_, i) => ({
      symbol: this.symbols[i % this.symbols.length],
      left: `${(i / 24) * 100 + (Math.random() - 0.5) * 6}%`,
      size: `${10 + Math.random() * 22}px`,
      duration: `${7 + Math.random() * 11}s`,
      delay: `${Math.random() * 10}s`,
      opacity: `${0.12 + Math.random() * 0.45}`,
    }));
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.loading.set(true);
    this.errorMsg.set('');
    this.authService.login(this.form.value).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/portal']);
      },
      error: err => {
        this.loading.set(false);
        this.errorMsg.set(
          err?.error?.detail ?? 'No se pudo conectar con el servidor. Intenta de nuevo.'
        );
      },
    });
  }

  isInvalid(field: string): boolean {
    const ctrl = this.form.get(field);
    return !!(ctrl?.invalid && ctrl?.touched);
  }
}
