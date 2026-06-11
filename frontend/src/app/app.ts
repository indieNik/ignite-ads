import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
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
  busy = signal<string>(''); // current operation label
  error = signal<string>('');
  showLaunch = signal(false);

  // launch form
  selectedRun = '';
  videoUrl = '';
  landingUrl = 'https://igniteai.in';
  budget = 10000; // minor units (₹100.00 on INR accounts)
  primaryText = '';
  headline = '';
  description = '';
  aiGenerated = false;

  ngOnInit() {
    watchUser((u) => {
      this.user.set(u);
      if (u) this.refresh();
    });
  }

  login() { login().catch((e) => this.error.set(e.message)); }
  logout() { logout(); this.campaigns.set([]); }

  async refresh() {
    try {
      this.busy.set('Loading campaigns…');
      const data = await apiFetch('/api/ads/campaigns');
      this.campaigns.set(data.campaigns || []);
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.busy.set('');
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
    this.busy.set('Asking Gemini for copy…');
    this.error.set('');
    try {
      const copy = await apiFetch('/api/ads/copy-suggest', {
        method: 'POST',
        body: JSON.stringify({ run_id: this.selectedRun || null, landing_url: this.landingUrl }),
      });
      this.primaryText = copy.primary_text;
      this.headline = copy.headline;
      this.description = copy.description;
      this.aiGenerated = true;
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.busy.set('');
    }
  }

  async launch() {
    this.error.set('');
    if (!this.selectedRun && !this.videoUrl) { this.error.set('Pick a video or paste a URL'); return; }
    if (!this.primaryText || !this.headline) { this.error.set('Copy required — use ✨ Suggest or type it'); return; }
    this.busy.set('Launching (PAUSED)…');
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
      this.pollUntilDone(res.launch_id);
    } catch (e: any) {
      this.error.set(e.message);
      this.busy.set('');
    }
  }

  private async pollUntilDone(launchId: string) {
    this.busy.set('Launching: video → creative → campaign → ad set → ad…');
    for (let i = 0; i < 90; i++) {
      await new Promise((r) => setTimeout(r, 5000));
      try {
        const launch = await apiFetch(`/api/ads/campaigns/${launchId}`);
        await this.refresh();
        if (launch.status !== 'launching' && launch.status !== 'draft') {
          this.busy.set('');
          if (launch.status === 'error') this.error.set(`Launch failed: ${launch.error}`);
          return;
        }
      } catch { /* transient — keep polling */ }
    }
    this.busy.set('');
  }

  async sync(c: Campaign) {
    this.busy.set('Syncing from Meta…');
    try {
      await apiFetch(`/api/ads/campaigns/${c.launch_id}/sync`, { method: 'POST' });
      await this.refresh();
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.busy.set('');
    }
  }

  async activate(c: Campaign) {
    const budget = (c.config?.daily_budget_cents / 100).toFixed(2);
    if (!confirm(`Start REAL AD SPEND for "${c.name}" at ${budget}/day (account currency)?`)) return;
    this.busy.set('Activating…');
    try {
      await apiFetch(`/api/ads/campaigns/${c.launch_id}/activate`, {
        method: 'POST', body: JSON.stringify({ confirm: true }),
      });
      await this.refresh();
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.busy.set('');
    }
  }

  async pause(c: Campaign) {
    this.busy.set('Pausing…');
    try {
      await apiFetch(`/api/ads/campaigns/${c.launch_id}/pause`, { method: 'POST' });
      await this.refresh();
    } catch (e: any) {
      this.error.set(e.message);
    } finally {
      this.busy.set('');
    }
  }

  adsManagerUrl(c: Campaign): string {
    const campaignId = c.platform_ids?.campaign_id;
    return `https://adsmanager.facebook.com/adsmanager/manage/campaigns?selected_campaign_ids=${campaignId}`;
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
}
