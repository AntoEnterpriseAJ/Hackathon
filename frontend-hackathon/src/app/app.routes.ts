import { Routes } from '@angular/router';
import { DiffPageComponent } from './diff/diff-page/diff-page.component';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./home/home.component').then((m) => m.HomeComponent)
  },
  {
    path: 'diff',
    component: DiffPageComponent
  },
  {
    path: '**',
    redirectTo: ''
  }
];
