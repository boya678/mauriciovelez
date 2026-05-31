import { CommonModule } from '@angular/common';
import { Component, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { COLOMBIA_DATA } from '../../core/data/colombia.data';
import { EmbajadoresService } from '../../core/services/embajadores.service';

@Component({
  selector: 'app-embajadores',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './embajadores.component.html',
  styleUrl: './embajadores.component.scss',
})
export class EmbajadoresComponent {
  readonly portalUrl = 'https://portal.mauricioveleznumerologo.com';
  readonly portalLoginUrl = 'https://portal.mauricioveleznumerologo.com/login';

  readonly beneficios = [
    {
      icon: 'attach_money',
      titulo: 'Comisiones reales',
      desc: 'Gana por cada usuario que se registre en el software con tu enlace de aliado.',
    },
    {
      icon: 'people',
      titulo: 'Red de aliados',
      desc: 'Haz parte de una comunidad exclusiva de líderes numerológicos en Colombia.',
    },
    {
      icon: 'school',
      titulo: 'Capacitación incluida',
      desc: 'Accede a material formativo y estrategias de Mauricio Vélez para crecer tu red.',
    },
    {
      icon: 'workspace_premium',
      titulo: 'Insignia de Oro',
      desc: 'Recibe tu credencial de Embajador de Oro y diferénciate en tu comunidad.',
    },
    {
      icon: 'support_agent',
      titulo: 'Soporte prioritario',
      desc: 'Canal de atención directo con el equipo para resolver dudas de tus referidos.',
    },
    {
      icon: 'trending_up',
      titulo: 'Ingresos escalables',
      desc: 'Sin techo de ganancias — cuantos más referidos activos, mayor tu ingreso mensual.',
    },
  ];

  step = signal<1 | 2 | 3>(1);
  codigoAsignado = signal('');

  nombre = '';
  celular = '';
  codigoPais = '57';
  correo = '';
  cc = '';
  departamento = '';
  ciudad = '';
  barrio = '';
  otpCode = '';

  loading = signal(false);
  errorMsg = signal('');
  successMsg = signal('');

  readonly departamentos = COLOMBIA_DATA.map((d) => d.dep);
  private readonly departamentoSig = signal('');

  readonly ciudadesDisponibles = computed(() => {
    const dep = this.departamentoSig();
    if (!dep) return [];
    return COLOMBIA_DATA.find((d) => d.dep === dep)?.ciudades ?? [];
  });

  constructor(private embajadoresService: EmbajadoresService) {}

  onDepartamentoChange(): void {
    this.departamentoSig.set(this.departamento);
    this.ciudad = '';
  }

  enviarCodigo(): void {
    this.errorMsg.set('');
    const nombre = this.nombre.trim();
    const celular = this.celular.trim();

    if (!nombre) {
      this.errorMsg.set('Ingresa tu nombre completo.');
      return;
    }

    if (!celular || celular.length < 7) {
      this.errorMsg.set('Ingresa un número de celular válido.');
      return;
    }

    this.loading.set(true);
    this.embajadoresService.sendRegistroOtp({ celular, codigo_pais: this.codigoPais }).subscribe({
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

  confirmar(): void {
    this.errorMsg.set('');
    const otp = this.otpCode.trim();

    if (otp.length !== 6) {
      this.errorMsg.set('El código debe tener 6 dígitos.');
      return;
    }

    this.loading.set(true);
    this.embajadoresService.registro({
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
      next: (res) => {
        this.loading.set(false);
        this.codigoAsignado.set(res.aliado?.codigo_vip ?? '');
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
