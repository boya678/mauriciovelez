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

  // Estado modal Referido
  showReferidoModal = signal(false);
  referidoCode = '';
  referidoError = signal('');
  referidoLoading = signal(false);
  private pendingLoginRes: any = null;

  // Estado modal OTP
  showOtpModal = signal(false);
  otpCode = '';
  otpError = signal('');
  otpLoading = signal(false);
  otpExpiraEn = 5;

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
    // Intentar login directo (sin OTP — clientes existentes pasan aquí)
    this.authService.login({ ...this.form.value }).subscribe({
      next: res => {
        this.loading.set(false);
        this.handleLoginSuccess(res);
      },
      error: err => {
        const detail = err?.error?.detail;
        if (err.status === 403 && detail === 'otp_required') {
          // Cliente nuevo: enviar OTP por WhatsApp y mostrar modal
          this.authService.sendOtp(this.form.value.celular).subscribe({
            next: res2 => {
              this.loading.set(false);
              this.otpExpiraEn = res2.expira_en;
              this.otpCode = '';
              this.otpError.set('');
              this.showOtpModal.set(true);
            },
            error: otpErr => {
              this.loading.set(false);
              this.errorMsg.set(otpErr?.error?.detail ?? 'No se pudo enviar el código. Intenta de nuevo.');
            },
          });
        } else {
          this.loading.set(false);
          this.errorMsg.set(typeof detail === 'string' ? detail : 'Error al ingresar');
        }
      },
    });
  }

  private handleLoginSuccess(res: any): void {
    if (res.cliente.vip) {
      this.pendingClienteId = res.cliente.id;
      this.vipCode = '';
      this.vipError.set('');
      this.showVipModal.set(true);
    } else {
      this.router.navigate(['/portal']);
    }
  }

  confirmOtp(): void {
    if (!this.otpCode.trim() || this.otpCode.length !== 6) {
      this.otpError.set('Ingresa el código de 6 dígitos');
      return;
    }
    this.otpLoading.set(true);
    this.otpError.set('');
    // Paso 2: login con OTP incluido (cliente nuevo)
    const payload = { ...this.form.value, otp_code: this.otpCode.trim() };
    this.authService.login(payload).subscribe({
      next: res => {
        this.otpLoading.set(false);
        this.showOtpModal.set(false);
        if (res.es_nuevo) {
          // Mostrar modal de referido antes de entrar al portal
          this.pendingLoginRes = res;
          this.referidoCode = '';
          this.referidoError.set('');
          this.showReferidoModal.set(true);
        } else {
          this.handleLoginSuccess(res);
        }
      },
      error: err => {
        this.otpLoading.set(false);
        const detail = err?.error?.detail;
        this.otpError.set(
          typeof detail === 'string' ? detail : 'Código incorrecto o expirado.'
        );
      },
    });
  }

  confirmReferido(): void {
    if (!this.referidoCode.trim()) {
      this.skipReferido();
      return;
    }
    this.referidoLoading.set(true);
    this.referidoError.set('');
    this.authService.saveReferido(this.referidoCode.trim()).subscribe({
      next: () => {
        this.referidoLoading.set(false);
        this.showReferidoModal.set(false);
        this.handleLoginSuccess(this.pendingLoginRes);
      },
      error: () => {
        this.referidoLoading.set(false);
        this.showReferidoModal.set(false);
        this.handleLoginSuccess(this.pendingLoginRes);
      },
    });
  }

  skipReferido(): void {
    this.showReferidoModal.set(false);
    this.handleLoginSuccess(this.pendingLoginRes);
  }

  cancelOtpModal(): void {
    this.showOtpModal.set(false);
    this.otpCode = '';
    this.otpError.set('');
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
