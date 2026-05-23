import { Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { COLOMBIA_DATA } from '../../../core/data/colombia.data';

@Component({
  selector: 'app-registro',
  standalone: true,
  imports: [FormsModule, CommonModule, RouterLink],
  templateUrl: './registro.component.html',
  styleUrl: './registro.component.scss',
})
export class RegistroComponent {
  // ── Stepper ──────────────────────────────────────────────────
  step = signal<1 | 2 | 3>(1);

  // ── Código asignado (paso 3) ─────────────────────────────────
  codigoAsignado = signal('');

  // ── Formulario paso 1 ────────────────────────────────────────
  nombre = '';
  celular = '';
  codigoPais = '57';
  correo = '';
  cc = '';
  departamento = '';
  ciudad = '';
  barrio = '';

  // ── OTP paso 2 ───────────────────────────────────────────────
  otpCode = '';

  // ── Estado UI ────────────────────────────────────────────────
  loading = signal(false);
  errorMsg = signal('');
  successMsg = signal('');

  // ── Datos Colombia ───────────────────────────────────────────
  readonly departamentos = COLOMBIA_DATA.map(d => d.dep);

  ciudadesDisponibles = computed(() => {
    const dep = this.departamentoSig();
    if (!dep) return [];
    return COLOMBIA_DATA.find(d => d.dep === dep)?.ciudades ?? [];
  });

  // Señal para reactivo en template
  private departamentoSig = signal('');

  onDepartamentoChange(): void {
    this.departamentoSig.set(this.departamento);
    this.ciudad = '';
  }

  constructor(private auth: AuthService, public router: Router) {}

  // ── Paso 1: enviar OTP ───────────────────────────────────────
  enviarCodigo(): void {
    this.errorMsg.set('');
    const nombre = this.nombre.trim();
    const celular = this.celular.trim();

    if (!nombre) { this.errorMsg.set('Ingresa tu nombre completo.'); return; }
    if (!celular || celular.length < 7) { this.errorMsg.set('Ingresa un número de celular válido.'); return; }

    this.loading.set(true);
    this.auth.sendRegistroOtp({ celular, codigo_pais: this.codigoPais }).subscribe({
      next: () => {
        this.loading.set(false);
        this.successMsg.set(`Código enviado a WhatsApp +${this.codigoPais} ${celular}`);
        this.step.set(2);
      },
      error: (err) => {
        this.loading.set(false);
        this.errorMsg.set(err?.error?.detail ?? 'Error al enviar el código. Intenta de nuevo.');
      },
    });
  }

  // ── Paso 2: confirmar OTP y registrar ────────────────────────
  confirmar(): void {
    this.errorMsg.set('');
    const otp = this.otpCode.trim();
    if (otp.length !== 6) { this.errorMsg.set('El código debe tener 6 dígitos.'); return; }

    this.loading.set(true);
    this.auth.registro({
      nombre: this.nombre.trim(),
      celular: this.celular.trim(),
      codigo_pais: this.codigoPais,
      correo: this.correo.trim() || null,
      cc: this.cc.trim() || null,
      departamento: this.departamento || null,
      ciudad: this.ciudad || null,
      barrio: this.barrio.trim() || null,
      otp_code: otp,
    }).subscribe({
      next: (res: any) => {
        this.loading.set(false);
        this.codigoAsignado.set(res?.aliado?.codigo_vip ?? '');
        this.step.set(3);
      },
      error: (err) => {
        this.loading.set(false);
        this.errorMsg.set(err?.error?.detail ?? 'Error al completar el registro. Intenta de nuevo.');
      },
    });
  }

  volverPaso1(): void {
    this.step.set(1);
    this.otpCode = '';
    this.errorMsg.set('');
    this.successMsg.set('');
  }
}
