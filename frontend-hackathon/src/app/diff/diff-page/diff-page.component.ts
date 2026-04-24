/**
 * DiffPageComponent - main page that orchestrates all diff components.
 */

import { Component, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiffService } from '../services/diff.service';
import { DiffResponse } from '../models/diff.models';
import { DiffUploadComponent } from '../components/diff-upload/diff-upload.component';
import { DiffViewerComponent } from '../components/diff-viewer/diff-viewer.component';
import { DiffSummaryComponent } from '../components/diff-summary/diff-summary.component';
import { LogicChangesComponent } from '../components/logic-changes/logic-changes.component';

@Component({
  selector: 'app-diff-page',
  standalone: true,
  imports: [
    CommonModule,
    DiffUploadComponent,
    DiffViewerComponent,
    DiffSummaryComponent,
    LogicChangesComponent
  ],
  templateUrl: './diff-page.component.html',
  styleUrls: ['./diff-page.component.scss']
})
export class DiffPageComponent {
  // Signals
  uploadState = signal<'idle' | 'loading' | 'done' | 'error'>('idle');
  diffResult = signal<DiffResponse | null>(null);
  errorMessage = signal<string | null>(null);

  constructor(private diffService: DiffService) {
    // Auto-validate service health
    effect(() => {
      this.diffService.health().subscribe({
        error: () => console.warn('Diff service not available')
      });
    });
  }

  onFilesSelected(files: { fileOld: File; fileNew: File }) {
    this.uploadState.set('loading');
    this.errorMessage.set(null);

    this.diffService.compare(files.fileOld, files.fileNew, 'fd').subscribe({
      next: (response: DiffResponse) => {
        this.diffResult.set(response);
        this.uploadState.set('done');
      },
      error: (err) => {
        console.error('Diff error:', err);
        this.errorMessage.set(err.error?.error || 'Failed to compare documents');
        this.uploadState.set('error');
      }
    });
  }

  resetResults() {
    this.diffResult.set(null);
    this.uploadState.set('idle');
    this.errorMessage.set(null);
  }
}
