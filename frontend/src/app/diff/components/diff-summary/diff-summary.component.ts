/**
 * DiffSummaryComponent - displays statistics about the diff.
 */

import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiffSummary } from '../../models/diff.models';

@Component({
  selector: 'app-diff-summary',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './diff-summary.component.html',
  styleUrls: ['./diff-summary.component.scss']
})
export class DiffSummaryComponent {
  summary = input<DiffSummary | undefined>(undefined);
}
