/**
 * LogicChangesComponent - displays semantic/logical changes.
 */

import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LogicChange } from '../../models/diff.models';

@Component({
  selector: 'app-logic-changes',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './logic-changes.component.html',
  styleUrls: ['./logic-changes.component.scss']
})
export class LogicChangesComponent {
  logicChanges = input<LogicChange[]>([]);

  getSeverityClass(severity: string): string {
    return 'severity-' + severity.toLowerCase();
  }

  getSeverityIcon(severity: string): string {
    switch (severity) {
      case 'HIGH':
        return '⚠️';
      case 'MEDIUM':
        return 'ℹ️';
      case 'LOW':
        return '✓';
      default:
        return '•';
    }
  }

  trackByChange(index: number): number {
    return index;
  }
}
