import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore } from '../case.store';
import { ExplorerPanelComponent } from '../explorer-panel/explorer-panel.component';
import { TabsAreaComponent } from '../tabs-area/tabs-area.component';
import { ChatRailComponent } from '../chat-rail/chat-rail.component';
import { StatusBarComponent } from '../status-bar/status-bar.component';
import { CommandPaletteComponent } from '../command-palette/command-palette.component';

@Component({
  selector: 'app-studio-shell',
  standalone: true,
  imports: [
    CommonModule,
    ExplorerPanelComponent,
    TabsAreaComponent,
    ChatRailComponent,
    StatusBarComponent,
    CommandPaletteComponent,
  ],
  templateUrl: './studio-shell.component.html',
  styleUrl: './studio-shell.component.scss',
})
export class StudioShellComponent {
  protected readonly store = inject(CaseStore);
}
