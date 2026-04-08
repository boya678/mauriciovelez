import { Component, Input, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BannerService, BannerPublico } from '../../core/services/banner.service';

@Component({
  selector: 'app-banner',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './banner.component.html',
  styleUrl: './banner.component.scss',
})
export class BannerComponent implements OnInit {
  @Input() esVip = false;

  banner = signal<BannerPublico | null>(null);
  visible = signal(false);

  constructor(private svc: BannerService) {}

  ngOnInit() {
    this.svc.getActivo(this.esVip).subscribe(b => {
      if (b) {
        this.banner.set(b);
        this.visible.set(true);
      }
    });
  }

  cerrar() {
    this.visible.set(false);
  }
}
