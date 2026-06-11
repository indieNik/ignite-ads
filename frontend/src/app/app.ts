import { CommonModule } from '@angular/common';
import { Component, HostListener, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { User } from 'firebase/auth';
import { apiFetch, login, logout, watchUser } from './firebase';

interface Campaign {
  launch_id: string;
  name: string;
  status: string;
  review_status?: string;
  video_url: string;
  config: any;
  copy: any;
  platform_ids: any;
  lifetime?: { impressions?: number; clicks?: number; spend?: number };
  created_at: number;
  error?: string;
}

interface Run {
  run_id: string;
  video_url: string;
  created_at: number;
  prompt: string;
}

interface Toast {
  id: number;
  kind: 'success' | 'error' | 'info';
  text: string;
}

interface ConfirmState {
  title: string;
  message: string;
  confirmText: string;
  onConfirm: () => void;
}

/** The Meta launch chain — mirrors the backend's step-resume state machine. */
const LAUNCH_STEPS: { key: string; label: string }[] = [
  { key: 'video_id', label: 'Video' },
  { key: 'creative_id', label: 'Creative' },
  { key: 'campaign_id', label: 'Campaign' },
  { key: 'adset_id', label: 'Ad set' },
  { key: 'ad_id', label: 'Ad' },
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  user = signal<User | null | undefined>(undefined); // undefined = booting
  campaigns = signal<Campaign[]>([]);
  runs = signal<Run[]>([]);
  loading = signal(true); // first campaigns fetch → skeletons
  error = signal<string>(''); // modal-scoped error
  showLaunch = signal(false);
  suggesting = signal(false);
  launching = signal(false);
  syncingId = signal<string>(''); // per-card sync spinner
  toasts = signal<Toast[]>([]);
  confirmState = signal<ConfirmState | null>(null);
  steps = LAUNCH_STEPS;

  // launch form
  selectedRun = '';
  videoUrl = '';
  landingUrl = 'https://igniteai.in';
  budget = 10000; // minor units (₹100.00 on INR accounts)
  primaryText = '';
  headline = '';
  description = '';
  aiGenerated = false;

  private toastSeq = 0;

  ngOnInit() {
    watchUser((u) => {
      this.user.set(u);
      if (u) this.refresh();
    });
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    if (this.confirmState()) this.confirmState.set(null);
    else if (this.showLaunch() && !this.launching()) this.showLaunch.set(false);
  }

  login() { login().catch((e) => this.toast('error', e.message)); }
  logout() { logout(); this.campaigns.set([]); }

  toast(kind: Toast['kind'], text: string) {
    const id = ++this.toastSeq;
    this.toasts.update((t) => [...t, { id, kind, text }]);
    setTimeout(() => this.dismissToast(id), 4500);
  }
  dismissToast(id: number) {
    this.toasts.update((t) => t.filter((x) => x.id !== id));
  }

  async refresh(silent = false) {
    try {
      const data = await apiFetch('/api/ads/campaigns');
      this.campaigns.set(data.campaigns || []);
    } catch (e: any) {
      if (!silent) this.toast('error', e.message);
    } finally {
      this.loading.set(false);
    }
  }

  async openLaunch() {
    this.showLaunch.set(true);
    this.error.set('');
    try {
      const data = await apiFetch('/api/ads/runs');
      this.runs.set(data.runs || []);
    } catch (e: any) {
      this.error.set(e.message);
    }
  }

  async suggestCopy() {
    this.suggesting.set(true);
    this.error.set('');
    this.primaryText = '';
    this.headline = '';
    this.description = '';
    try {
      const copy = await apiFetch('/api/ads/copy-suggest', {
        method: 'POST',
        body: JSON.stringify({ run_id: this.selectedRun || null, landing_url: this.landingUrl }),
      });
      await this.typewrite('primaryText', copy.primary_text);
      await this.typewrite('headline', copy.headline);
      await this.typewrite('description', copy.description);
      this.aiGenerated = true;
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.suggesting.set(false);
    }
  }

  /** Reveal AI copy character-by-character — feedback that something was generated. */
  private async typewrite(field: 'primaryText' | 'headline' | 'description', text: string) {
    const t = text || '';
    const step = Math.max(1, Math.round(t.length / 30));
    for (let i = 0; i <= t.length; i += step) {
      (this as any)[field] = t.slice(0, i);
      await new Promise((r) => setTimeout(r, 16));
    }
    (this as any)[field] = t;
  }

  async launch() {
    this.error.set('');
    if (!this.selectedRun && !this.videoUrl) { this.error.set('Pick a video or paste a URL'); return; }
    if (!this.primaryText || !this.headline) { this.error.set('Copy required — use ✨ Suggest or type it'); return; }
    this.launching.set(true);
    try {
      const res = await apiFetch('/api/ads/launch', {
        method: 'POST',
        body: JSON.stringify({
          run_id: this.selectedRun || null,
          video_url: this.videoUrl || null,
          daily_budget_cents: this.budget,
          landing_url: this.landingUrl,
          primary_text: this.primaryText,
          headline: this.headline,
          description: this.description,
          ai_generated: this.aiGenerated,
        }),
      });
      this.showLaunch.set(false);
      this.toast('info', 'Launch started — building the chain on Meta. Everything stays paused.');
      await this.refresh(true);
      this.pollUntilDone(res.launch_id);
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.launching.set(false);
    }
  }

  /** Poll while launching — the campaign card's stepper lights up live. */
  private async pollUntilDone(launchId: string) {
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      try {
        const launch = await apiFetch(`/api/ads/campaigns/${launchId}`);
        await this.refresh(true);
        if (launch.status !== 'launching' && launch.status !== 'draft') {
          if (launch.status === 'error') {
            this.toast('error', `Launch failed: ${launch.error}`);
          } else {
            this.toast('success', `“${launch.copy?.headline || launch.name}” is live in Ads Manager — paused and ready.`);
          }
          return;
        }
      } catch { /* transient — keep polling */ }
    }
  }

  async sync(c: Campaign) {
    this.syncingId.set(c.launch_id);
    try {
      await apiFetch(`/api/ads/campaigns/${c.launch_id}/sync`, { method: 'POST' });
      await this.refresh(true);
      this.toast('success', 'Synced with Meta.');
    } catch (e: any) {
      this.toast('error', e.message);
    } finally {
      this.syncingId.set('');
    }
  }

  activate(c: Campaign) {
    const budget = `${this.currencySymbol(c)}${(c.config?.daily_budget_cents / 100).toFixed(0)}/day`;
    this.confirmState.set({
      title: 'Start real ad spend?',
      message: `“${c.copy?.headline || c.name}” will go live on Meta at ${budget}. You can pause it anytime.`,
      confirmText: `Activate at ${budget}`,
      onConfirm: async () => {
        this.confirmState.set(null);
        try {
          await apiFetch(`/api/ads/campaigns/${c.launch_id}/activate`, {
            method: 'POST', body: JSON.stringify({ confirm: true }),
          });
          await this.refresh(true);
          this.toast('success', 'Campaign activated — delivery starts after Meta finishes review.');
        } catch (e: any) {
          this.toast('error', e.message);
        }
      },
    });
  }

  async pause(c: Campaign) {
    try {
      await apiFetch(`/api/ads/campaigns/${c.launch_id}/pause`, { method: 'POST' });
      await this.refresh(true);
      this.toast('success', 'Campaign paused.');
    } catch (e: any) {
      this.toast('error', e.message);
    }
  }

  // ---------- view helpers ----------

  adsManagerUrl(c: Campaign): string {
    return `https://adsmanager.facebook.com/adsmanager/manage/campaigns?selected_campaign_ids=${c.platform_ids?.campaign_id}`;
  }

  statusClass(s: string): string {
    const map: Record<string, string> = {
      active: 'badge live', paused: 'badge paused',
      launching: 'badge launching', error: 'badge error', rejected: 'badge error',
    };
    return map[s] || 'badge';
  }

  /** Only surface Meta's status when it adds information beyond ours. */
  reviewChip(c: Campaign): string {
    const r = (c.review_status || '').toUpperCase();
    if (!r || r === 'UNKNOWN') return '';
    const redundant: Record<string, string> = {
      paused: 'PAUSED', active: 'ACTIVE', rejected: 'DISAPPROVED',
    };
    return redundant[c.status] === r ? '' : r.replace(/_/g, ' ');
  }

  currencySymbol(c: Campaign): string {
    const map: Record<string, string> = { INR: '₹', USD: '$', EUR: '€', GBP: '£' };
    return map[c.config?.currency] ?? '';
  }

  fmtDate(ts: number): string {
    if (!ts) return '';
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  runLabel(r: Run): string {
    const date = this.fmtDate(r.created_at);
    const prompt = (r.prompt || '').slice(0, 60) || r.run_id.slice(0, 16);
    return `${date} · ${prompt}`;
  }

  stepDone(c: Campaign, key: string): boolean {
    return !!c.platform_ids?.[key];
  }

  /** Index of the step currently executing (first one without an id). */
  stepCurrent(c: Campaign): number {
    return this.steps.findIndex((s) => !c.platform_ids?.[s.key]);
  }
}
