import { Component, OnInit, signal, HostListener } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService, Aliado } from '../../../core/services/auth.service';

interface NavItem {
  label: string;
  icon: string;
  route: string;
}

@Component({
  selector: 'app-portal-layout',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommonModule],
  templateUrl: './portal-layout.component.html',
  styleUrl: './portal-layout.component.scss',
})
export class PortalLayoutComponent implements OnInit {
  aliado = signal<Aliado | null>(null);
  sidebarOpen = signal(true);
  mobileMenuOpen = signal(false);

  navItems: NavItem[] = [
    { label: 'Mis Referidos', icon: 'group', route: '/portal/referidos' },
    { label: 'Mi Perfil',     icon: 'manage_accounts', route: '/portal/mis-datos' },
  ];

  constructor(private auth: AuthService, private router: Router) {}

  ngOnInit(): void {
    this.aliado.set(this.auth.getAliado());
    // Refresh from server
    this.auth.getPerfil().subscribe({ next: a => this.aliado.set(a), error: () => {} });
    // Responsive default
    this.sidebarOpen.set(window.innerWidth > 768);
  }

  @HostListener('window:resize')
  onResize(): void {
    if (window.innerWidth > 768) this.mobileMenuOpen.set(false);
  }

  get inicial(): string {
    const n = this.aliado()?.nombre ?? '';
    return n.charAt(0).toUpperCase();
  }

  get roleLabel(): string {
    const t = this.aliado()?.tipo_cliente;
    if (t === 3) return '★★ Aliado Tipo 3';
    if (t === 2) return '★ Aliado Tipo 2';
    return 'Aliado';
  }

  get saldoFmt(): string {
    const s = this.aliado()?.saldo ?? 0;
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(s);
  }

  toggleSidebar(): void {
    if (window.innerWidth <= 768) {
      this.mobileMenuOpen.update(v => !v);
    } else {
      this.sidebarOpen.update(v => !v);
    }
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
