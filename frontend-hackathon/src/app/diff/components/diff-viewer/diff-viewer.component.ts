/**
 * DiffViewerComponent - displays diffs in git-style table format.
 */

import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SectionDiff, LineDiff, InlineDiff } from '../../models/diff.models';

@Component({
  selector: 'app-diff-viewer',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './diff-viewer.component.html',
  styleUrls: ['./diff-viewer.component.scss']
})
export class DiffViewerComponent {
  sectionDiffs = input<SectionDiff[]>([]);

  getStatusBadge(status: string): string {
    switch (status) {
      case 'equal':
        return '=';
      case 'modified':
        return '≈';
      case 'added':
        return '+';
      case 'removed':
        return '-';
      default:
        return '?';
    }
  }

  getStatusColor(status: string): string {
    switch (status) {
      case 'equal':
        return 'gray';
      case 'modified':
        return 'yellow';
      case 'added':
        return 'green';
      case 'removed':
        return 'red';
      default:
        return 'gray';
    }
  }

  getLineBgClass(type: string): string {
    switch (type) {
      case 'equal':
        return 'line-equal';
      case 'remove':
        return 'line-remove';
      case 'add':
        return 'line-add';
      case 'replace':
        return 'line-replace';
      default:
        return '';
    }
  }

  trackBySection(index: number): number {
    return index;
  }

  trackByLine(index: number): number {
    return index;
  }
}
