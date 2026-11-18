/**
 * Production-ready, Responsive HTML Email Templates for NovexTrade
 * Compatible with all major email clients (Gmail, Apple Mail, Outlook, Yahoo).
 */

export interface WelcomeEmailParams {
  name: string;
  dashboardUrl?: string;
  supportEmail?: string;
}

export interface PriceAlertEmailParams {
  ticker: string;
  companyName: string;
  type: 'above' | 'below';
  conditionPrice: string;
  currentPrice: string;
  change: string;
  timestamp?: string;
  dashboardUrl?: string;
}

export interface ReEngagementEmailParams {
  name: string;
  marketHighlights?: string;
  dashboardUrl?: string;
}

export interface NewsSummaryEmailParams {
  dateStr: string;
  dashboardUrl?: string;
  articles: Array<{
    title: string;
    bullets: string[];
    url: string;
  }>;
}

export function escapeHtml(str: string = ''): string {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function sanitizeUrl(url: string = '', fallback: string = '#/dashboard'): string {
  if (!url) return fallback;
  const trimmed = url.trim();
  if (trimmed.startsWith('#/') || trimmed.startsWith('/') || /^https?:\/\//i.test(trimmed)) {
    return escapeHtml(trimmed);
  }
  return fallback;
}

// Base Wrapper for Dark Theme Emails
const emailWrapper = (content: string, preheaderText: string = '') => `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NovexTrade Notification</title>
  <style>
    body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
    table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
    img { -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }
    body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; background-color: #0b0e11; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    @media screen and (max-width: 600px) {
      .email-container { width: 100% !important; padding: 16px !important; }
    }
  </style>
</head>
<body style="margin: 0; padding: 24px 0; background-color: #0b0e11; color: #eaecef;">
  <!-- Hidden Preheader Text -->
  <div style="display: none; font-size: 1px; color: #0b0e11; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden;">
    ${escapeHtml(preheaderText)}
  </div>

  <table border="0" cellpadding="0" cellspacing="0" width="100%">
    <tr>
      <td align="center">
        <table class="email-container" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 520px; background-color: #12141c; border: 1px solid #1f2433; border-radius: 12px; overflow: hidden; padding: 28px 24px;">
          <!-- Header / Brand Logo -->
          <tr>
            <td style="padding-bottom: 24px;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="left">
                    <div style="display: inline-flex; align-items: center;">
                      <span style="display: inline-block; width: 26px; height: 26px; border-radius: 6px; background-color: rgba(240, 185, 11, 0.15); border: 1px solid rgba(240, 185, 11, 0.4); text-align: center; line-height: 26px; color: #f0b90b; font-weight: 800; font-size: 15px;">N</span>
                      <span style="font-size: 20px; font-weight: 800; color: #ffffff; margin-left: 8px; letter-spacing: -0.5px;">NovexTrade</span>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td>
              ${content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding-top: 28px; border-top: 1px solid #1c2130; margin-top: 24px; text-align: center; font-size: 11px; color: #64748b;">
              <p style="margin: 0 0 8px;">You're receiving this email because you registered on NovexTrade Institutional Exchange.</p>
              <p style="margin: 0 0 12px;">
                <a href="#/settings" style="color: #f0b90b; text-decoration: underline;">Unsubscribe</a> &nbsp;•&nbsp; 
                <a href="#/dashboard" style="color: #f0b90b; text-decoration: underline;">Visit NovexTrade</a>
              </p>
              <p style="margin: 0; color: #475569;">© 2026 NovexTrade Inc. All rights reserved.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
`;

/**
 * 1. Welcome to NovexTrade Email
 */
export function generateWelcomeEmail(params: WelcomeEmailParams): string {
  const safeName = escapeHtml(params.name || 'there');
  const safeDashboardUrl = sanitizeUrl(params.dashboardUrl, '#/dashboard');

  const content = `
    <!-- Mockup Hero Image -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px; background: #0c0e14; border: 1px solid #1a1e2b; border-radius: 8px; overflow: hidden;">
      <tr>
        <td style="padding: 16px; text-align: center;">
          <div style="background: #141722; border-radius: 6px; padding: 12px; border: 1px solid #232838;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="color: #0ecb81; font-weight: 700; font-size: 11px;">● BTC/USDT +2.84%</span>
              <span style="color: #f0b90b; font-weight: 700; font-size: 11px;">ETH $3,450.20</span>
            </div>
            <div style="height: 60px; background: linear-gradient(180deg, rgba(14, 203, 129, 0.15) 0%, rgba(14, 203, 129, 0) 100%); border-bottom: 2px solid #0ecb81; border-radius: 4px;"></div>
          </div>
        </td>
      </tr>
    </table>

    <h1 style="font-size: 20px; font-weight: 800; color: #ffffff; margin: 0 0 14px; letter-spacing: -0.3px;">
      Welcome to NovexTrade Institutional Exchange
    </h1>

    <p style="font-size: 13.5px; line-height: 1.55; color: #94a3b8; margin: 0 0 16px;">
      Thanks for joining NovexTrade, ${safeName}! You now have direct access to ultra-low latency matching, deterministic double-entry accounting, and institutional liquidity pools. Here's what you can do right now:
    </p>

    <ul style="padding-left: 20px; margin: 0 0 20px; font-size: 13px; line-height: 1.6; color: #cbd5e1;">
      <li><strong>Explore live order books</strong> and institutional market depth</li>
      <li><strong>Access Strategy Resources</strong> for institutional playbooks and algorithmic research</li>
      <li><strong>Set up price alerts</strong> to monitor high-frequency volatility triggers</li>
    </ul>

    <div style="background-color: #171b26; border-left: 3px solid #f0b90b; padding: 12px 14px; border-radius: 4px; margin-bottom: 24px;">
      <p style="font-size: 12.5px; line-height: 1.5; color: #94a3b8; margin: 0;">
        Institutional Grade: 100% solvency verification, deterministic price-time priority execution, and cold-storage proof of reserves.
      </p>
    </div>

    <!-- CTA Button -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%">
      <tr>
        <td align="center">
          <a href="${safeDashboardUrl}" style="display: block; width: 100%; background-color: #f0b90b; color: #0b0e11; font-size: 14px; font-weight: 800; text-align: center; text-decoration: none; padding: 14px 0; border-radius: 6px; box-sizing: border-box;">
            Launch Terminal
          </a>
        </td>
      </tr>
    </table>
  `;

  return emailWrapper(content, `Welcome to NovexTrade, ${safeName}! Launch your trading terminal today.`);
}

/**
 * 2 & 3. Price Alert Trigger Email (Above / Below)
 */
export function generatePriceAlertEmail(params: PriceAlertEmailParams): string {
  const isAbove = params.type === 'above';
  const bannerBg = isAbove ? '#133926' : '#4a151b';
  const bannerBorder = isAbove ? '#10b981' : '#ef4444';
  const bannerText = isAbove ? 'Price Above Reached' : 'Price Below Hit';
  const bannerColor = isAbove ? '#34d399' : '#f87171';
  const priceColor = isAbove ? '#0ecb81' : '#f87171';

  const safeTicker = escapeHtml(params.ticker);
  const safeCompany = escapeHtml(params.companyName);
  const safePrice = escapeHtml(params.currentPrice);
  const safeCondPrice = escapeHtml(params.conditionPrice);
  const safeChange = escapeHtml(params.change);
  const safeTime = escapeHtml(params.timestamp || 'Today at ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  const safeDashboardUrl = sanitizeUrl(params.dashboardUrl, '#/spot');

  const content = `
    <!-- Alert Banner -->
    <div style="background-color: ${bannerBg}; border: 1px solid ${bannerBorder}; border-radius: 8px; padding: 12px 16px; text-align: center; margin-bottom: 20px;">
      <div style="font-size: 15px; font-weight: 800; color: ${bannerColor}; text-transform: uppercase; letter-spacing: 0.5px;">
        ${bannerText}
      </div>
      <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;">
        ${safeTime}
      </div>
    </div>

    <!-- Stock Card -->
    <div style="background-color: #161a24; border: 1px solid #232a3b; border-radius: 8px; padding: 18px; text-align: center; margin-bottom: 20px;">
      <div style="font-size: 14px; font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">
        ${safeTicker} — ${safeCompany}
      </div>
      <div style="font-size: 11px; color: #64748b; margin-bottom: 8px;">Trigger Price</div>
      <div style="font-size: 32px; font-weight: 900; color: ${priceColor}; font-family: monospace; letter-spacing: -0.5px;">
        ${safePrice}
      </div>
    </div>

    <!-- Alert Details Box -->
    <div style="background-color: #161a24; border: 1px solid #232a3b; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
      <div style="font-size: 12.5px; font-weight: 800; color: #ffffff; margin-bottom: 8px;">Alert Execution Details:</div>
      <p style="font-size: 12px; color: #94a3b8; margin: 0 0 10px;">
        Target trigger for <strong>${safeCompany} (${safeTicker})</strong> has matched current market depth.
      </p>
      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-size: 12px; color: #cbd5e1; font-family: monospace;">
        <tr>
          <td style="padding: 3px 0; color: #64748b;">Condition:</td>
          <td align="right" style="padding: 3px 0; font-weight: 700; color: #ffffff;">Price ${isAbove ? '≥' : '≤'} ${safeCondPrice}</td>
        </tr>
        <tr>
          <td style="padding: 3px 0; color: #64748b;">Current Price:</td>
          <td align="right" style="padding: 3px 0; font-weight: 700; color: ${priceColor};">${safePrice}</td>
        </tr>
        <tr>
          <td style="padding: 3px 0; color: #64748b;">Change:</td>
          <td align="right" style="padding: 3px 0; font-weight: 700; color: ${isAbove ? '#0ecb81' : '#f87171'};">${safeChange}</td>
        </tr>
      </table>
    </div>

    <!-- CTA Button -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%">
      <tr>
        <td align="center">
          <a href="${safeDashboardUrl}" style="display: block; width: 100%; background-color: #f0b90b; color: #0b0e11; font-size: 14px; font-weight: 800; text-align: center; text-decoration: none; padding: 14px 0; border-radius: 6px; box-sizing: border-box;">
            Trade ${safeTicker} Now
          </a>
        </td>
      </tr>
    </table>
  `;

  return emailWrapper(content, `[${safeTicker}] hit price trigger at ${safePrice} on NovexTrade`);
}

/**
 * 4. Re-engagement Email ("We Miss You")
 */
export function generateReEngagementEmail(params: ReEngagementEmailParams): string {
  const safeName = escapeHtml(params.name || 'Valued Trader');
  const safeHighlights = escapeHtml(params.marketHighlights || 'High-volume trading pairs have shown elevated volatility and breakout liquidity over the past 24 hours.');
  const safeDashboardUrl = sanitizeUrl(params.dashboardUrl, '#/dashboard');

  const content = `
    <h1 style="font-size: 20px; font-weight: 800; color: #ffffff; margin: 0 0 16px; letter-spacing: -0.3px;">
      Market Liquidity Update, ${safeName}
    </h1>

    <p style="font-size: 13.5px; line-height: 1.55; color: #94a3b8; margin: 0 0 16px;">
      Dear ${safeName},
    </p>

    <p style="font-size: 13.5px; line-height: 1.55; color: #94a3b8; margin: 0 0 20px;">
      We noticed you haven't opened your NovexTrade terminal recently. High-frequency market-making and liquidity pools have shifted across top pairs:
    </p>

    <!-- Market Update Box -->
    <div style="background-color: #161a24; border: 1px solid #232a3b; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
      <div style="font-size: 12.5px; font-weight: 800; color: #f0b90b; margin-bottom: 6px;">Institutional Brief:</div>
      <p style="font-size: 12px; line-height: 1.5; color: #cbd5e1; margin: 0;">
        ${safeHighlights}
      </p>
    </div>

    <!-- CTA Button -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%">
      <tr>
        <td align="center">
          <a href="${safeDashboardUrl}" style="display: block; width: 100%; background-color: #f0b90b; color: #0b0e11; font-size: 14px; font-weight: 800; text-align: center; text-decoration: none; padding: 14px 0; border-radius: 6px; box-sizing: border-box;">
            Resume Trading
          </a>
        </td>
      </tr>
    </table>
  `;

  return emailWrapper(content, `Institutional update for ${safeName} on NovexTrade`);
}

/**
 * 5. Daily Market News Summary Email
 */
export function generateNewsSummaryEmail(params: NewsSummaryEmailParams): string {
  const safeDate = escapeHtml(params.dateStr || 'Current Market Cycle');
  const safeDashboardUrl = sanitizeUrl(params.dashboardUrl, '#/news');

  const articlesHtml = params.articles.map((art) => `
    <div style="background-color: #161a24; border: 1px solid #232a3b; border-radius: 8px; padding: 18px; margin-bottom: 18px;">
      <h3 style="font-size: 14.5px; font-weight: 800; color: #ffffff; line-height: 1.4; margin: 0 0 10px;">
        ${escapeHtml(art.title)}
      </h3>
      <ul style="padding-left: 18px; margin: 0 0 12px; font-size: 12px; line-height: 1.55; color: #94a3b8;">
        ${art.bullets.map(b => `<li style="margin-bottom: 6px;">${escapeHtml(b)}</li>`).join('')}
      </ul>
      <div>
        <a href="${sanitizeUrl(art.url, '#/news')}" style="font-size: 11.5px; font-weight: 700; color: #f0b90b; text-decoration: none;">
          Read Analysis →
        </a>
      </div>
    </div>
  `).join('');

  const content = `
    <div style="margin-bottom: 20px;">
      <h1 style="font-size: 20px; font-weight: 800; color: #ffffff; margin: 0 0 4px; letter-spacing: -0.3px;">
        NovexTrade Intelligence Digest
      </h1>
      <div style="font-size: 11.5px; color: #64748b; font-weight: 600;">
        ${safeDate}
      </div>
    </div>

    ${articlesHtml}

    <!-- View More in Dashboard Button -->
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top: 10px;">
      <tr>
        <td align="center">
          <a href="${safeDashboardUrl}" style="display: block; width: 100%; background-color: #232838; color: #ffffff; border: 1px solid #333a4c; font-size: 13px; font-weight: 700; text-align: center; text-decoration: none; padding: 12px 0; border-radius: 6px; box-sizing: border-box;">
            Open Terminal Intelligence
          </a>
        </td>
      </tr>
    </table>
  `;

  return emailWrapper(content, `NovexTrade Market Intelligence - ${safeDate}`);
}
