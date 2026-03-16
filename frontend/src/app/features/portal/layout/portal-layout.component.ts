import { BreakpointObserver, Breakpoints } from '@angular/cdk/layout';
import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive, Router, NavigationEnd } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subscription, filter } from 'rxjs';
import { AuthService, Cliente } from '../../../core/services/auth.service';

export interface MenuItem {
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
export class PortalLayoutComponent implements OnInit, OnDestroy {
  collapsed = signal(false);
  isMobile = signal(false);
  cliente: Cliente | null = null;
  vipFin: string | null = null;
  private subs = new Subscription();

  menuItems: MenuItem[] = [
    { label: 'Numerología', icon: 'auto_awesome', route: '/portal/numerologia' },
  ];

  get vipMenuItems(): MenuItem[] {
    if (!this.cliente?.vip) return [];
    return [{ label: 'Mis Datos', icon: 'manage_accounts', route: '/portal/mis-datos' }];
  }

  constructor(
    private authService: AuthService,
    private router: Router,
    private breakpoint: BreakpointObserver,
  ) {}

  ngOnInit(): void {
    this.cliente = this.authService.getCliente();

    // Cargar fecha de vencimiento VIP si aplica
    if (this.cliente?.vip) {
      this.subs.add(
        this.authService.getMiSuscripcion().subscribe(res => {
          this.vipFin = res.fin;
        })
      );
    }

    // Detectar móvil y colapsar automáticamente
    this.subs.add(
      this.breakpoint.observe([Breakpoints.Handset, Breakpoints.TabletPortrait]).subscribe(state => {
        this.isMobile.set(state.matches);
        this.collapsed.set(state.matches);
      })
    );

    // En móvil, colapsar al navegar
    this.subs.add(
      this.router.events.pipe(filter(e => e instanceof NavigationEnd)).subscribe(() => {
        if (this.isMobile()) this.collapsed.set(true);
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  get inicial(): string {
    return (this.cliente?.nombre?.[0] ?? 'U').toUpperCase();
  }

  toggle(): void {
    this.collapsed.update(v => !v);
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/login']);
  }
}
