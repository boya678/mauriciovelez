import { Component, HostListener, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent {
  readonly year = new Date().getFullYear();
  readonly menuOpen = signal(false);
  readonly scrolled = signal(false);

  readonly softwareUrl = 'https://portal.mauricioveleznumerologo.com/';
  readonly softwareName = 'Software Numerológico';
  readonly softwarePromo = 'Primera victoria gratis';
  readonly whatsappNumber = '3225556333';
  readonly whatsappUrl =
    'https://wa.me/57' + this.whatsappNumber +
    '?text=' + encodeURIComponent('Hola Mauricio, me interesa tu método numerológico.');

  readonly navItems = [
    { path: '/', label: 'Inicio', icon: 'home' },
  ];

  @HostListener('window:scroll')
  onScroll(): void {
    this.scrolled.set(window.scrollY > 8);
  }

  toggleMenu(): void {
    this.menuOpen.update((v) => !v);
  }

  closeMenu(): void {
    this.menuOpen.set(false);
  }
}
