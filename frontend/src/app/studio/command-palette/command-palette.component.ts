import {
  Component,
  HostListener,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { CaseStore, ToolKind } from '../case.store';

interface Command {
  id: string;
  icon: string;
  label: string;
  hint?: string;
  run: () => void;
}

@Component({
  selector: 'app-command-palette',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './command-palette.component.html',
  styleUrl: './command-palette.component.scss',
})
export class CommandPaletteComponent {
  private readonly store = inject(CaseStore);
  protected readonly open = signal(false);
  protected readonly query = signal('');

  protected readonly commands = computed<Command[]>(() => {
    const tools: { kind: ToolKind; icon: string; label: string; hint: string }[] =
      [
        { kind: 'diff', icon: '🔍', label: 'Open Diff', hint: 'Ctrl+1' },
        { kind: 'sync', icon: '🔗', label: 'Open Sync', hint: 'Ctrl+2' },
        { kind: 'migrate', icon: '🔄', label: 'Open Migrate', hint: 'Ctrl+3' },
        { kind: 'draft', icon: '📝', label: 'Open Draft', hint: 'Ctrl+4' },
        { kind: 'validate', icon: '✅', label: 'Open Validate', hint: 'Ctrl+5' },
      ];
    return tools.map((t) => ({
      id: `tool:${t.kind}`,
      icon: t.icon,
      label: t.label,
      hint: t.hint,
      run: () => this.store.openToolTab(t.kind),
    }));
  });

  protected readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const cmds = this.commands();
    if (!q) return cmds;
    return cmds.filter((c) => c.label.toLowerCase().includes(q));
  });

  protected readonly recentDocs = computed(() =>
    [...this.store.documents()]
      .sort((a, b) => b.addedAt - a.addedAt)
      .slice(0, 5),
  );

  @HostListener('window:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      this.open.update((v) => !v);
      this.query.set('');
      return;
    }
    if (this.open() && e.key === 'Escape') {
      this.open.set(false);
      return;
    }
    if (mod && /^[1-5]$/.test(e.key)) {
      e.preventDefault();
      const tools: ToolKind[] = ['diff', 'sync', 'migrate', 'draft', 'validate'];
      this.store.openToolTab(tools[parseInt(e.key, 10) - 1]);
    }
  }

  protected runCommand(c: Command): void {
    c.run();
    this.open.set(false);
  }

  protected openDoc(id: string): void {
    this.store.openDocumentTab(id);
    this.open.set(false);
  }

  protected close(): void {
    this.open.set(false);
  }
}
