import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CaseStore,
  DocumentKind,
  ToolKind,
  guessKindFromFilename,
} from '../case.store';

interface ToolDescriptor {
  kind: ToolKind;
  icon: string;
  label: string;
  /** Required document kinds that must exist in the Case to enable the tool. */
  requires: DocumentKind[];
}

const TOOLS: ToolDescriptor[] = [
  { kind: 'diff', icon: '🔍', label: 'Diff', requires: ['fd', 'fd'] },
  { kind: 'sync', icon: '🔗', label: 'Sync', requires: ['fd', 'plan'] },
  { kind: 'migrate', icon: '🔄', label: 'Migrate', requires: ['fd', 'template'] },
  { kind: 'draft', icon: '📝', label: 'Draft FD', requires: ['plan'] },
  { kind: 'validate', icon: '✅', label: 'Validate', requires: ['fd'] },
];

@Component({
  selector: 'app-explorer-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './explorer-panel.component.html',
  styleUrl: './explorer-panel.component.scss',
})
export class ExplorerPanelComponent {
  protected readonly store = inject(CaseStore);
  protected readonly tools = TOOLS;

  protected readonly kindLabels: Record<DocumentKind, string> = {
    fd: 'Fișa Disciplinei',
    plan: 'Plan de Învățământ',
    template: 'Template',
    other: 'Other',
  };

  /** Returns true if every required kind has at least one document. */
  protected toolEnabled(tool: ToolDescriptor): boolean {
    const buckets = this.store.documentsByKind();
    // Count requirements per kind so 'fd' twice means we need 2 FDs.
    const need: Record<string, number> = {};
    for (const k of tool.requires) need[k] = (need[k] ?? 0) + 1;
    for (const k of Object.keys(need)) {
      if ((buckets[k as DocumentKind]?.length ?? 0) < need[k]) return false;
    }
    return true;
  }

  protected toolTooltip(tool: ToolDescriptor): string {
    if (this.toolEnabled(tool)) return `Open ${tool.label}`;
    const missing = tool.requires
      .map((k) => this.kindLabels[k])
      .join(' + ');
    return `Add ${missing} to enable`;
  }

  protected onFiles(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files) return;
    for (const f of Array.from(input.files)) {
      this.store.addDocument(f, guessKindFromFilename(f.name));
    }
    input.value = '';
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (!files) return;
    for (const f of Array.from(files)) {
      this.store.addDocument(f, guessKindFromFilename(f.name));
    }
  }

  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  protected openDocument(id: string): void {
    this.store.openDocumentTab(id);
  }

  protected openTool(tool: ToolDescriptor): void {
    if (!this.toolEnabled(tool)) return;
    this.store.openToolTab(tool.kind);
  }

  protected removeDocument(event: Event, id: string): void {
    event.stopPropagation();
    this.store.removeDocument(id);
  }

  protected kinds: DocumentKind[] = ['fd', 'plan', 'template', 'other'];
}
