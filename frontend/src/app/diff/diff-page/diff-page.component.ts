/**
 * DiffPageComponent - main page that orchestrates visual diff components.
 */

import { Component, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiffService } from '../services/diff.service';
import { DiffUploadComponent } from '../components/diff-upload/diff-upload.component';
import { DiffViewerComponent } from '../components/diff-viewer/diff-viewer.component';
import { SectionDiff, DiffSummary } from '../models/diff.models';
import { HttpErrorResponse } from '@angular/common/http';

@Component({
  selector: 'app-diff-page',
  standalone: true,
  imports: [
    CommonModule,
    DiffUploadComponent,
    DiffViewerComponent,
  ],
  templateUrl: './diff-page.component.html',
  styleUrls: ['./diff-page.component.scss']
})
export class DiffPageComponent implements OnInit {
  // Signals
  visualState = signal<'idle' | 'loading' | 'done' | 'error'>('idle');
  sections = signal<SectionDiff[]>([]);
  summary = signal<DiffSummary | null>(null);
  errorMessage = signal<string | null>(null);
  serviceOnline = signal<boolean | null>(null);

  constructor(private diffService: DiffService) { }

  ngOnInit(): void {
    this.diffService.health().subscribe({
      next: () => this.serviceOnline.set(true),
      error: () => {
        this.serviceOnline.set(false);
        console.warn('Diff service not available');
      }
    });
  }

  onFilesSelected(files: { fileOld: File; fileNew: File }) {
    this.visualState.set('loading');
    this.errorMessage.set(null);
    this.sections.set([]);
    this.summary.set(null);

    this.diffService.compare(files.fileOld, files.fileNew).subscribe({
      next: (res) => {
        this.sections.set(res.sections);
        this.summary.set(res.summary);
        this.visualState.set('done');
      },
      error: (err) => {
        console.error('Diff error:', err);
        this.errorMessage.set(this.buildDiffErrorMessage(err));
        this.visualState.set('error');
      }
    });
  }

  private buildDiffErrorMessage(err: unknown): string {
    const fallback = 'Failed to generate diff.';

    if (err instanceof HttpErrorResponse) {
      const backendMessage =
        (typeof err.error === 'string' ? err.error : err.error?.error) ||
        err.message;

      if (backendMessage) {
        return backendMessage;
      }

      if (err.status === 0) {
        return 'Failed to reach diff service. Make sure backend is running on port 5000.';
      }
    }

    return fallback;
  }

  resetResults() {
    this.sections.set([]);
    this.summary.set(null);
    this.visualState.set('idle');
    this.errorMessage.set(null);
  }
}
