import { Component, HostListener, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './layout.component.html',
  styleUrl: './layout.component.scss',
})
export class LayoutComponent {
  sidebarOpen = signal(true);

  constructor(public auth: AuthService) {}

  @HostListener('window:resize')
  onResize() {
    if (window.innerWidth < 768) this.sidebarOpen.set(false);
  }

  ngOnInit() {
    if (window.innerWidth < 768) this.sidebarOpen.set(false);
  }

  toggle() { this.sidebarOpen.update(v => !v); }
}
