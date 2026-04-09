import { Component, OnInit, signal } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
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
  imports: [ReactiveFormsModule, FormsModule, CommonModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent implements OnInit {
  form!: FormGroup;
  loading = signal(false);
  errorMsg = signal('');
  particles: Particle[] = [];
  recordar = false;

  private readonly STORAGE_KEY = 'mv_recordar';

  // Estado modal VIP
  showVipModal = signal(false);
  vipCode = '';
  vipError = signal('');
  vipLoading = signal(false);
  private pendingClienteId = '';

  // Estado modal cuenta deshabilitada
  showDisabledModal = signal(false);
  disabledMsg = signal('');

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
    const saved = this.loadSaved();
    this.recordar = !!saved;
    this.form = this.fb.group({
      nombre: [saved?.nombre ?? '', [Validators.required, Validators.minLength(2)]],
      celular: [saved?.celular ?? '', [Validators.required, Validators.pattern(/^\d{10}$/)]],
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

  private loadSaved(): { nombre: string; celular: string } | null {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    if (this.recordar) {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.form.value));
    } else {
      localStorage.removeItem(this.STORAGE_KEY);
    }
    this.loading.set(true);
    this.errorMsg.set('');
    this.authService.login(this.form.value).subscribe({
      next: res => {
        this.loading.set(false);
        if (res.cliente.vip) {
          this.pendingClienteId = res.cliente.id;
          this.vipCode = '';
          this.vipError.set('');
          this.showVipModal.set(true);
        } else {
          this.router.navigate(['/portal']);
        }
      },
      error: err => {
        this.loading.set(false);
        const detail = err?.error?.detail;
        if (detail?.code === 'CLIENTE_DISABLED') {
          this.disabledMsg.set(detail.message);
          this.showDisabledModal.set(true);
        } else {
          this.errorMsg.set(
            typeof detail === 'string' ? detail : 'No se pudo conectar con el servidor. Intenta de nuevo.'
          );
        }
      },
    });
  }

  submitVipCode(): void {
    if (!this.vipCode.trim()) {
      this.vipError.set('Ingresa tu código VIP');
      return;
    }
    this.vipLoading.set(true);
    this.vipError.set('');
    this.authService.verifyVip(this.pendingClienteId, this.vipCode.trim()).subscribe({
      next: () => {
        this.vipLoading.set(false);
        this.showVipModal.set(false);
        this.router.navigate(['/portal']);
      },
      error: err => {
        this.vipLoading.set(false);
        this.vipError.set(
          err?.error?.detail ?? 'Código incorrecto. Intenta de nuevo.'
        );
      },
    });
  }

  cancelVipModal(): void {
    this.showVipModal.set(false);
    this.authService.logout();
    this.vipCode = '';
    this.vipError.set('');
    this.pendingClienteId = '';
  }

  isInvalid(field: string): boolean {
    const ctrl = this.form.get(field);
    return !!(ctrl?.invalid && ctrl?.touched);
  }
}
