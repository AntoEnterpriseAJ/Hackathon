import { Routes } from '@angular/router';
import { DiffPageComponent } from './diff/diff-page/diff-page.component';

// Lazy loaders reused for both new (`/`) and legacy (`/legacy/*`) mount points.
const homeLoader = () =>
  import('./home/home.component').then((m) => m.HomeComponent);
const syncLoader = () =>
  import('./sync-check/sync-check-page/sync-check-page.component').then(
    (m) => m.SyncCheckPageComponent,
  );
const draftLoader = () =>
  import('./draft/draft-page/draft-page.component').then(
    (m) => m.DraftPageComponent,
  );
const templateShiftLoader = () =>
  import(
    './template-shift/template-shift-page/template-shift-page.component'
  ).then((m) => m.TemplateShiftPageComponent);
const studioLoader = () =>
  import('./studio/studio-shell/studio-shell.component').then(
    (m) => m.StudioShellComponent,
  );

export const routes: Routes = [
  // New Studio shell at root.
  { path: '', loadComponent: studioLoader },

  // Legacy multi-page UI lives under /legacy/* during the migration.
  { path: 'legacy', loadComponent: homeLoader },
  { path: 'legacy/diff', component: DiffPageComponent },
  { path: 'legacy/sync', loadComponent: syncLoader },
  { path: 'legacy/draft', loadComponent: draftLoader },
  { path: 'legacy/template-shift', loadComponent: templateShiftLoader },

  // Keep the original short paths working as aliases so any existing
  // bookmarks or copy-pasted links still resolve.
  { path: 'diff', component: DiffPageComponent },
  { path: 'sync', loadComponent: syncLoader },
  { path: 'draft', loadComponent: draftLoader },
  { path: 'template-shift', loadComponent: templateShiftLoader },

  { path: '**', redirectTo: '' },
];
