/**
 * NovexTrade Referral Attribution Utility
 * Captures ?ref=CODE from URL, persists across refreshes and navigation via
 * localStorage + cookie, and records server-side click attribution.
 */

const REF_CODE_KEY = 'novextrade_ref_code';
const REF_CLICK_ID_KEY = 'novextrade_ref_click_id';

function setCookie(name: string, value: string, days = 30) {
  try {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
  } catch {
    // ignore cookie errors in restricted contexts
  }
}

function getCookie(name: string): string | null {
  try {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  } catch {
    return null;
  }
}

export function getStoredReferral(): { referralCode: string | null; clickId: string | null } {
  if (typeof window === 'undefined') return { referralCode: null, clickId: null };
  const code = localStorage.getItem(REF_CODE_KEY) || getCookie(REF_CODE_KEY);
  const clickId = localStorage.getItem(REF_CLICK_ID_KEY) || getCookie(REF_CLICK_ID_KEY);
  return {
    referralCode: code ? code.trim().toUpperCase() : null,
    clickId: clickId || null,
  };
}

export async function captureReferralFromUrl(): Promise<string | null> {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const rawRef = params.get('ref') || params.get('referral');
  if (!rawRef || !rawRef.trim()) {
    return getStoredReferral().referralCode;
  }

  const code = rawRef.trim().toUpperCase();
  const prevCode = localStorage.getItem(REF_CODE_KEY);
  localStorage.setItem(REF_CODE_KEY, code);
  setCookie(REF_CODE_KEY, code, 30);

  // Record click on server once per code change or fresh visit
  const sessionKey = `novextrade_ref_tracked_${code}`;
  if (!sessionStorage.getItem(sessionKey) || prevCode !== code) {
    sessionStorage.setItem(sessionKey, '1');
    try {
      const res = await fetch('/api/v1/referrals/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          referralCode: code,
          landingPath: window.location.pathname + window.location.search,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.clickId) {
          localStorage.setItem(REF_CLICK_ID_KEY, data.clickId);
          setCookie(REF_CLICK_ID_KEY, data.clickId, 30);
        }
      }
    } catch {
      // non-fatal network error
    }
  }
  return code;
}
