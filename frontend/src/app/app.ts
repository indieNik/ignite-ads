import { CommonModule } from '@angular/common';
import { Component, HostListener, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { User } from 'firebase/auth';
import { apiFetch, login, logout, watchUser } from './firebase';

interface VariantMetric {
  index: number;
  ad_id: string;
  headline: string;
  impressions: number;
  clicks: number;
  spend: number;
  ctr: number;
}

interface Campaign {
  launch_id: string;
  name: string;
  status: string;
  review_status?: string;
  video_url: string;
  config: any;
  copy: any;
  copy_variants?: any[];
  num_variants?: number;
  platform_ids: any;
  lifetime?: { impressions?: number; clicks?: number; spend?: number };
  daily?: { date: string; impressions: number; clicks: number; spend: number }[];
  variant_metrics?: VariantMetric[];
  ads?: { index: number; ad_id: string; effective_status: string; headline: string }[];
  created_at: number;
  error?: string;
}

interface VariantForm {
  primaryText: string;
  headline: string;
  description: string;
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

/** Minimum impressions before crowning an A/B winner — below this it's noise. */
const TOP_VARIANT_MIN_IMPRESSIONS = 100;

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

  // launch form
  selectedRun = '';
  videoUrl = '';
  landingUrl = 'https://igniteai.in';
  budget = 10000; // minor units (₹100.00 on INR accounts)
  numVariants = 1; // A/B test: one ad per copy variant, same video + adset
  activeVariant = 0;
  // Always 3 slots — the count control only changes how many are shown and
  // submitted. Truncating here would destroy copy when toggling 3 → 2 → 3.
  variants: VariantForm[] = Array.from({ length: 3 }, () => this.emptyVariant());
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

  emptyVariant(): VariantForm {
    return { primaryText: '', headline: '', description: '' };
  }

  setNumVariants(n: number) {
    this.numVariants = n;
    if (this.activeVariant >= n) this.activeVariant = n - 1;
  }

  /** The variants currently in play (shown as tabs, sent on launch). */
  shownVariants(): VariantForm[] {
    return this.variants.slice(0, this.numVariants);
  }

  async suggestCopy() {
    this.suggesting.set(true);
    this.error.set('');
    for (let i = 0; i < this.numVariants; i++) this.variants[i] = this.emptyVariant();
    this.activeVariant = 0;
    try {
      const res = await apiFetch('/api/ads/copy-suggest', {
        method: 'POST',
        body: JSON.stringify({
          run_id: this.selectedRun || null,
          landing_url: this.landingUrl,
          num_variants: this.numVariants,
        }),
      });
      const suggestions = res.variants || [res];
      for (let i = 0; i < this.numVariants && i < suggestions.length; i++) {
        this.activeVariant = i; // typewrite into the visible tab
        await this.typewrite(i, 'primaryText', suggestions[i].primary_text);
        await this.typewrite(i, 'headline', suggestions[i].headline);
        await this.typewrite(i, 'description', suggestions[i].description);
      }
      this.activeVariant = 0;
      this.aiGenerated = true;
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.suggesting.set(false);
    }
  }

  /** Reveal AI copy character-by-character — feedback that something was generated. */
  private async typewrite(vi: number, field: keyof VariantForm, text: string) {
    const t = text || '';
    const step = Math.max(1, Math.round(t.length / 30));
    for (let i = 0; i <= t.length; i += step) {
      this.variants[vi][field] = t.slice(0, i);
      await new Promise((r) => setTimeout(r, 16));
    }
    this.variants[vi][field] = t;
  }

  async launch() {
    this.error.set('');
    if (!this.selectedRun && !this.videoUrl) { this.error.set('Pick a video or paste a URL'); return; }
    const active = this.shownVariants();
    const incomplete = active.findIndex((v) => !v.primaryText || !v.headline);
    if (incomplete >= 0) {
      this.activeVariant = incomplete;
      this.error.set(this.numVariants > 1
        ? `Variant ${incomplete + 1} needs copy — use ✨ Suggest or type it`
        : 'Copy required — use ✨ Suggest or type it');
      return;
    }
    this.launching.set(true);
    try {
      const res = await apiFetch('/api/ads/launch', {
        method: 'POST',
        body: JSON.stringify({
          run_id: this.selectedRun || null,
          video_url: this.videoUrl || null,
          daily_budget_cents: this.budget,
          landing_url: this.landingUrl,
          variants: active.map((v) => ({
            primary_text: v.primaryText, headline: v.headline, description: v.description,
          })),
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

  /** The Meta launch chain for this campaign — mirrors the backend's
   * step-resume state machine, one creative+ad pair per copy variant. */
  stepsFor(c: Campaign): { key: string; label: string }[] {
    const n = c.num_variants || 1;
    const steps = [
      { key: 'video_id', label: 'Video' },
      { key: 'campaign_id', label: 'Campaign' },
      { key: 'adset_id', label: 'Ad set' },
    ];
    for (let i = 0; i < n; i++) {
      const v = n > 1 ? ` v${i + 1}` : '';
      steps.push({ key: `creative_id_${i}`, label: `Creative${v}` });
      steps.push({ key: `ad_id_${i}`, label: `Ad${v}` });
    }
    return steps;
  }

  stepDone(c: Campaign, key: string): boolean {
    if (c.platform_ids?.[key]) return true;
    // pre-variant docs persisted singular creative_id/ad_id
    if (key === 'creative_id_0') return !!c.platform_ids?.creative_id;
    if (key === 'ad_id_0') return !!c.platform_ids?.ad_id;
    return false;
  }

  /** Index of the step currently executing (first one without an id). */
  stepCurrent(c: Campaign): number {
    return this.stepsFor(c).findIndex((s) => !this.stepDone(c, s.key));
  }

  /** Daily impressions normalized into the sparkline's 120×28 viewBox. */
  sparkPoints(c: Campaign): string {
    const days = c.daily || [];
    if (days.length < 2) return '';
    const vals = days.map((d) => d.impressions || 0);
    const min = Math.min(...vals);
    const range = Math.max(...vals) - min || 1;
    const w = 120, h = 28, pad = 2;
    return vals
      .map((v, i) => {
        const x = pad + (i * (w - 2 * pad)) / (vals.length - 1);
        const y = h - pad - ((v - min) / range) * (h - 2 * pad);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }

  /** Winning variant index by CTR — only once it has enough impressions. */
  topVariant(c: Campaign): number {
    const eligible = (c.variant_metrics || [])
      .filter((m) => (m.impressions || 0) >= TOP_VARIANT_MIN_IMPRESSIONS && m.ctr > 0);
    if ((c.variant_metrics?.length || 0) < 2 || !eligible.length) return -1;
    return eligible.reduce((a, b) => (b.ctr > a.ctr ? b : a)).index;
  }
}
