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
    path: 'sync',
    loadComponent: () =>
      import('./sync-check/sync-check-page/sync-check-page.component').then((m) => m.SyncCheckPageComponent)
  },
  {
    path: 'draft',
    loadComponent: () =>
      import('./draft/draft-page/draft-page.component').then((m) => m.DraftPageComponent)
  },
  {
    path: 'template-shift',
    loadComponent: () =>
      import('./template-shift/template-shift-page/template-shift-page.component').then(
        (m) => m.TemplateShiftPageComponent,
      )
  },
  {
    path: '**',
    redirectTo: ''
  }
];
