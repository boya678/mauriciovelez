import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { SuperadminAuthService } from '../../../core/services/superadmin-auth.service';

@Component({
  selector: 'app-sa-layout',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './sa-layout.component.html',
  styleUrl: './sa-layout.component.scss',
})
export class SaLayoutComponent {
  constructor(public auth: SuperadminAuthService) {}
}
