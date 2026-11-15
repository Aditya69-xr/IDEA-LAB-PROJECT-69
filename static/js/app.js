/**
 * SmartVision - Idea Lab Face Recognition Attendance Client
 */

class SmartVisionClient {
    constructor() {
        this.audioCtx = null;
        this.isAudioMuted = localStorage.getItem('sv_audio_muted') === 'true';
        this.lastSeenEventId = null;
        this.pollInterval = null;
        this.init();
    }

    init() {
        // Prepare Web Audio Context on first user click to bypass autoplay restrictions
        document.addEventListener('click', () => {
            this.ensureAudioContext();
        }, { once: true });

        // Start background polling if feed container exists
        if (document.getElementById('live-feed-container') || document.getElementById('kiosk-feed-container')) {
            this.startLiveEventPolling();
        }

        // Hardware page terminal auto-refresh
        if (document.getElementById('terminal-logs-window')) {
            this.startHardwarePolling();
        }
    }

    ensureAudioContext() {
        if (!this.audioCtx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.audioCtx = new AudioContext();
            }
        }
        if (this.audioCtx && this.audioCtx.state === 'suspended') {
            this.audioCtx.resume();
        }
    }

    // Synthesize pleasant two-tone positive chime
    playSuccessChime() {
        if (this.isAudioMuted) return;
        this.ensureAudioContext();
        if (!this.audioCtx) return;

        const now = this.audioCtx.currentTime;

        // Note 1: E5 (659.25 Hz)
        const osc1 = this.audioCtx.createOscillator();
        const gain1 = this.audioCtx.createGain();
        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(659.25, now);
        gain1.gain.setValueAtTime(0.2, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        osc1.connect(gain1);
        gain1.connect(this.audioCtx.destination);
        osc1.start(now);
        osc1.stop(now + 0.35);

        // Note 2: B5 (987.77 Hz) slightly delayed
        const osc2 = this.audioCtx.createOscillator();
        const gain2 = this.audioCtx.createGain();
        osc2.type = 'sine';
        osc2.frequency.setValueAtTime(987.77, now + 0.12);
        gain2.gain.setValueAtTime(0.22, now + 0.12);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
        osc2.connect(gain2);
        gain2.connect(this.audioCtx.destination);
        osc2.start(now + 0.12);
        osc2.stop(now + 0.55);
    }

    // Synthesize double warning buzz
    playWarningBuzz() {
        if (this.isAudioMuted) return;
        this.ensureAudioContext();
        if (!this.audioCtx) return;

        const now = this.audioCtx.currentTime;
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();

        osc.type = 'triangle';
        osc.frequency.setValueAtTime(320, now);
        osc.frequency.setValueAtTime(260, now + 0.1);

        gain.gain.setValueAtTime(0.25, now);
        gain.gain.setValueAtTime(0.01, now + 0.08);
        gain.gain.setValueAtTime(0.25, now + 0.12);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.3);
    }

    toggleAudioMute() {
        this.isAudioMuted = !this.isAudioMuted;
        localStorage.setItem('sv_audio_muted', this.isAudioMuted);
        const icon = document.getElementById('audio-mute-icon');
        if (icon) {
            icon.className = this.isAudioMuted ? 'fa-solid fa-volume-xmark text-danger' : 'fa-solid fa-volume-high text-success';
        }
    }

    startLiveEventPolling() {
        setInterval(() => {
            fetch('/api/live_events')
                .then(r => r.json())
                .then(data => {
                    this.handleLiveEventsUpdate(data);
                })
                .catch(err => console.debug("Poll error:", err));
        }, 1500);
    }

    handleLiveEventsUpdate(data) {
        if (!data || !data.events) return;

        // Update top counters if present
        const presentEl = document.getElementById('stat-today-present');
        if (presentEl && data.today_present !== undefined) {
            presentEl.innerText = data.today_present;
        }

        const events = data.events;
        if (events.length === 0) return;

        const latest = events[events.length - 1];
        const eventSig = `${latest.student_id}_${latest.time}_${latest.type}`;

        if (this.lastSeenEventId !== eventSig) {
            this.lastSeenEventId = eventSig;

            if (latest.type === 'MARKED_PRESENT' || latest.type === 'MANUAL_ENTRY') {
                this.playSuccessChime();
                this.renderFeedCard(latest, true);
                if (window.showLiveToast) {
                    window.showLiveToast(latest.message || "Attendance Confirmed!", "success");
                }
            } else if (latest.type === 'ALREADY_MARKED') {
                this.playWarningBuzz();
                this.renderFeedCard(latest, false);
            }
        }
    }

    renderFeedCard(event, isSuccess) {
        const container = document.getElementById('live-feed-container') || document.getElementById('kiosk-feed-container');
        if (!container) return;

        const div = document.createElement('div');
        div.className = 'feed-item animate__animated animate__fadeInDown';
        
        const photoSrc = event.snapshot_path ? `/static/${event.snapshot_path}` : '/static/img/avatar_placeholder.png';
        const badgeClass = isSuccess ? 'badge-status-present' : 'badge-status-sim';
        const badgeText = isSuccess ? 'PRESENT' : 'ALREADY RECORDED';

        div.innerHTML = `
            <img src="${photoSrc}" class="feed-avatar" onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(event.student_name)}&background=1e293b&color=fff'">
            <div class="flex-grow-1">
                <div class="d-flex justify-content-between align-items-center">
                    <strong class="text-white">${event.student_name}</strong>
                    <span class="${badgeClass}">${badgeText}</span>
                </div>
                <div class="d-flex justify-content-between text-muted small mt-1">
                    <span>${event.student_id} • ${event.department || 'Idea Lab'}</span>
                    <span>${event.time}</span>
                </div>
            </div>
        `;

        // Prepend to top and keep max 8 items
        container.insertBefore(div, container.firstChild);
        while (container.children.length > 8) {
            container.removeChild(container.lastChild);
        }
    }

    startHardwarePolling() {
        setInterval(() => {
            fetch('/api/hardware/status')
                .then(r => r.json())
                .then(data => {
                    const term = document.getElementById('terminal-logs-window');
                    if (term && data.recent_logs) {
                        term.innerHTML = data.recent_logs.map(l => {
                            let cl = 'terminal-rx';
                            if (l.status === 'SENT') cl = 'terminal-tx';
                            else if (l.status === 'SIMULATED') cl = 'terminal-sim';
                            else if (l.status === 'FAILED') cl = 'terminal-err';
                            return `<div class="terminal-line"><span class="text-muted">[${l.timestamp}]</span> <span class="${cl}">[${l.command}]</span> ${l.details || l.status}</div>`;
                        }).join('');
                    }
                })
                .catch(() => {});
        }, 2000);
    }
}

// Global instance
window.svClient = new SmartVisionClient();
