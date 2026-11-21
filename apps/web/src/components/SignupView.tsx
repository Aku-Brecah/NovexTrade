import React, { useState, useEffect } from 'react';
import { getStoredReferral, captureReferralFromUrl } from '../utils/referralAttribution';
import { useSignIn, useSignUp } from '@clerk/clerk-react';
import {
  Layers,
  Mail,
  Lock,
  User as UserIcon,
  Eye,
  EyeOff,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  CheckCircle2
} from 'lucide-react';

interface SignupViewProps {
  initialMode?: 'signup' | 'login';
  onSuccess: (user: any, token: string) => void;
  onNavigateHome: () => void;
}

export const SignupView: React.FC<SignupViewProps> = ({
  initialMode = 'login',
  onSuccess,
  onNavigateHome
}) => {
  const { signIn, setActive: setSignInActive } = useSignIn();
  const { signUp, setActive: setSignUpActive } = useSignUp();

  const [mode, setMode] = useState<'signup' | 'login' | 'forgot' | 'reset'>(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (window.location.pathname.includes('reset-password') || params.get('token')) {
        return 'reset';
      }
      if (window.location.pathname.includes('forgot-password')) {
        return 'forgot';
      }
    }
    return initialMode;
  });
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [requires2FA, setRequires2FA] = useState(false);
  const [resetToken, setResetToken] = useState(() => {
    if (typeof window !== 'undefined') {
      return new URLSearchParams(window.location.search).get('token') || '';
    }
    return '';
  });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (mode === 'login' || mode === 'signup') {
      setMode(initialMode);
    }
    setError(null);
    setSuccessMessage(null);
    setRequires2FA(false);
  }, [initialMode]);

  const validateStrongPassword = (pwd: string): string | null => {
    if (!pwd || pwd.length < 8) return 'Password must be at least 8 characters long.';
    if (!/[A-Z]/.test(pwd)) return 'Password must include at least one uppercase letter.';
    if (!/[a-z]/.test(pwd)) return 'Password must include at least one lowercase letter.';
    if (!/[0-9]/.test(pwd)) return 'Password must include at least one number.';
    return null;
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      // FORGOT PASSWORD FLOW
      if (mode === 'forgot') {
        const cleanEmail = email.trim().toLowerCase();
        if (!cleanEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
          throw new Error('Please enter a valid email address.');
        }
        const res = await fetch('/api/v1/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: cleanEmail }),
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          throw new Error(data.error || data.detail || 'Unable to process password reset request.');
        }
        setSuccessMessage(data.message || 'If an account exists for that email, a reset link has been sent.');
        return;
      }

      // RESET PASSWORD FLOW
      if (mode === 'reset') {
        if (!resetToken.trim()) throw new Error('Password reset token is required.');
        const pwdErr = validateStrongPassword(password);
        if (pwdErr) throw new Error(pwdErr);
        if (password !== confirmPassword) throw new Error('Passwords do not match.');

        const res = await fetch('/api/v1/auth/reset-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: resetToken.trim(),
            newPassword: password,
            confirmPassword,
          }),
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          throw new Error(data.error || data.detail || 'Password reset failed.');
        }
        setSuccessMessage('Password updated successfully! Please sign in with your new password.');
        setPassword('');
        setConfirmPassword('');
        setTimeout(() => setMode('login'), 1200);
        return;
      }

      const cleanEmail = email.trim().toLowerCase();
      if (!cleanEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
        throw new Error('Please enter a valid email address.');
      }

      if (mode === 'signup') {
        if (!fullName.trim()) throw new Error('Please enter your full name.');
        const pwdErr = validateStrongPassword(password);
        if (pwdErr) throw new Error(pwdErr);
        if (password !== confirmPassword) throw new Error('Passwords do not match.');

        // 1. Optional Clerk Sign-Up sync
        if (signUp) {
          try {
            const signUpAttempt = await signUp.create({
              emailAddress: cleanEmail,
              password,
              firstName: fullName.trim() || undefined
            });
            if (signUpAttempt.status === 'complete' && setSignUpActive) {
              await setSignUpActive({ session: signUpAttempt.createdSessionId });
            }
          } catch (clerkErr: any) {
            console.debug('Clerk signup notice:', clerkErr?.errors?.[0]?.message || clerkErr);
          }
        }

        // 2. Register with authoritative backend (preserving referral attribution)
        await captureReferralFromUrl();
        const { referralCode, clickId } = getStoredReferral();
        const res = await fetch('/api/v1/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: cleanEmail,
            password,
            confirmPassword,
            fullName: fullName.trim(),
            referralCode: referralCode || undefined,
            referralClickId: clickId || undefined,
          })
        });
        const data = await res.json();
        if (res.ok && data.success && data.token) {
          localStorage.setItem('syncnode_token', data.token);
          if (data.refreshToken) localStorage.setItem('syncnode_refresh_token', data.refreshToken);
          if (data.user) localStorage.setItem('syncnode_user', JSON.stringify(data.user));

          setSuccessMessage('Account created successfully! Loading dashboard...');
          setTimeout(() => {
            onSuccess(data.user, data.token);
          }, 300);
          return;
        }
        throw new Error(data.error || data.detail || 'Failed to register account.');
      }

      // LOGIN FLOW
      if (!password) throw new Error('Please enter your password.');

      if (signIn) {
        try {
          const signInAttempt = await signIn.create({
            identifier: cleanEmail,
            password
          });
          if (signInAttempt.status === 'complete' && setSignInActive) {
            await setSignInActive({ session: signInAttempt.createdSessionId });
          }
        } catch (clerkErr: any) {
          console.debug('Clerk signin notice:', clerkErr?.errors?.[0]?.message || clerkErr);
        }
      }

      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: cleanEmail,
          password,
          totpCode: requires2FA && totpCode.trim() ? totpCode.trim() : undefined,
        })
      });
      const data = await res.json();
      if (data.requires2FA) {
        setRequires2FA(true);
        setError('Two-factor authentication is enabled. Please enter your 6-digit authenticator code.');
        return;
      }
      if (res.ok && data.success && data.token) {
        localStorage.setItem('syncnode_token', data.token);
        if (data.refreshToken) localStorage.setItem('syncnode_refresh_token', data.refreshToken);
        if (data.user) localStorage.setItem('syncnode_user', JSON.stringify(data.user));

        setSuccessMessage('Signed in successfully! Entering terminal...');
        setTimeout(() => {
          onSuccess(data.user, data.token);
        }, 300);
        return;
      }
      throw new Error(data.error || data.detail || 'Invalid email or password.');
    } catch (err: any) {
      setError(err?.message || 'Authentication error. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError(null);
    try {
      const authObj = mode === 'signup' ? signUp : signIn;
      if (authObj && authObj.authenticateWithRedirect) {
        await authObj.authenticateWithRedirect({
          strategy: 'oauth_google',
          redirectUrl: `${window.location.origin}/`,
          redirectUrlComplete: `${window.location.origin}/dashboard`
        });
        return;
      }
      throw new Error('Clerk Google OAuth is initializing. Please try again.');
    } catch (err: any) {
      console.warn('Google sign in error:', err);
      setError(err?.errors?.[0]?.message || err?.message || 'Unable to connect to Google OAuth.');
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - 64px)',
        padding: '24px 16px',
        backgroundColor: '#0b0e11'
      }}
    >
      {/* Brand Header */}
      <div
        onClick={onNavigateHome}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: '24px',
          cursor: 'pointer'
        }}
      >
        <div className="brand-logo-badge">
          <div className="brand-logo-icon" style={{ width: '38px', height: '38px' }}>
            <Layers size={20} color="#f0b90b" />
          </div>
          <div className="brand-logo-text-wrap">
            <span className="brand-name-novex" style={{ fontSize: '22px' }}>NOVEX</span>
            <span className="brand-name-trade" style={{ fontSize: '22px' }}>TRADE</span>
          </div>
        </div>
      </div>

      {/* Main Clean Card */}
      <div
        style={{
          background: '#181a20',
          border: '1px solid #2b313a',
          borderRadius: '14px',
          padding: '26px 28px',
          maxWidth: '420px',
          width: '100%',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.4)'
        }}
      >
        {/* Top Tab Switcher */}
        <div
          style={{
            display: 'flex',
            background: '#0b0e11',
            border: '1px solid #2b313a',
            borderRadius: '8px',
            padding: '3px',
            marginBottom: '20px',
            gap: '4px'
          }}
        >
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setError(null);
              setSuccessMessage(null);
            }}
            style={{
              flex: 1,
              padding: '9px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '13.5px',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              background: mode === 'login' ? '#f0b90b' : 'transparent',
              color: mode === 'login' ? '#0b0e11' : '#848e9c'
            }}
          >
            Sign In
          </button>

          <button
            type="button"
            onClick={() => {
              setMode('signup');
              setError(null);
              setSuccessMessage(null);
            }}
            style={{
              flex: 1,
              padding: '9px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '13.5px',
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              background: mode === 'signup' ? '#f0b90b' : 'transparent',
              color: mode === 'signup' ? '#0b0e11' : '#848e9c'
            }}
          >
            Create Account
          </button>
        </div>

        {/* 1-Click Google Login Button via Clerk */}
        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={loading}
          style={{
            width: '100%',
            height: '42px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '10px',
            background: '#202630',
            border: '1px solid #2b313a',
            borderRadius: '8px',
            color: '#eaecef',
            fontSize: '13.5px',
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
            transition: 'background 0.15s ease',
            marginBottom: '16px'
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = '#29313d')}
          onMouseLeave={(e) => (e.currentTarget.style.background = '#202630')}
        >
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
          </svg>
          <span>Continue with Google</span>
        </button>

        {/* Clean Divider */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            margin: '14px 0 16px',
            color: '#5e6673',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.5px'
          }}
        >
          <div style={{ flex: 1, height: '1px', background: '#23272e' }} />
          <span style={{ padding: '0 10px' }}>OR</span>
          <div style={{ flex: 1, height: '1px', background: '#23272e' }} />
        </div>

        {/* Status Alerts */}
        {error && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(246, 70, 93, 0.12)',
              border: '1px solid rgba(246, 70, 93, 0.3)',
              borderRadius: '6px',
              padding: '9px 12px',
              color: '#f6465d',
              fontSize: '12.5px',
              marginBottom: '14px'
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {successMessage && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(14, 203, 129, 0.12)',
              border: '1px solid rgba(14, 203, 129, 0.3)',
              borderRadius: '6px',
              padding: '9px 12px',
              color: '#0ecb81',
              fontSize: '12.5px',
              marginBottom: '14px'
            }}
          >
            <CheckCircle2 size={15} style={{ flexShrink: 0 }} />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Clean Form */}
        {mode === 'signup' && getStoredReferral().referralCode && (
          <div className="nvx-alert nvx-alert-info" style={{ marginBottom: '12px', padding: '8px 12px', fontSize: '12px' }}>
            <CheckCircle2 size={14} style={{ flexShrink: 0 }} />
            <span>
              Partner invitation active: <strong className="nvx-mono-code">{getStoredReferral().referralCode}</strong>
            </span>
          </div>
        )}
        <form onSubmit={handleAuthSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Full Name for Sign Up */}
          {mode === 'signup' && (
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#848e9c', marginBottom: '5px' }}>
                Full Name
              </label>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  background: '#0b0e11',
                  border: '1px solid #2b313a',
                  borderRadius: '6px',
                  padding: '0 10px',
                  height: '40px'
                }}
              >
                <UserIcon size={15} color="#848e9c" style={{ marginRight: '8px' }} />
                <input
                  type="text"
                  placeholder="e.g. Satoshi Nakamoto"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  style={{
                    flex: 1,
                    background: 'transparent',
                    border: 'none',
                    outline: 'none',
                    color: '#eaecef',
                    fontSize: '13px'
                  }}
                  required={mode === 'signup'}
                />
              </div>
            </div>
          )}

          {/* Email */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#848e9c', marginBottom: '5px' }}>
              Email Address
            </label>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                background: '#0b0e11',
                border: '1px solid #2b313a',
                borderRadius: '6px',
                padding: '0 10px',
                height: '40px'
              }}
            >
              <Mail size={15} color="#848e9c" style={{ marginRight: '8px' }} />
              <input
                type="email"
                placeholder="trader@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#eaecef',
                  fontSize: '13px'
                }}
                required
              />
            </div>
          </div>

          {/* Reset Token (only in reset mode) */}
          {mode === 'reset' && (
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#848e9c', marginBottom: '5px' }}>
                Reset Token
              </label>
              <input
                type="text"
                className="nvx-input nvx-mono-code"
                placeholder="Paste reset token from email"
                value={resetToken}
                onChange={(e) => setResetToken(e.target.value)}
                required
              />
            </div>
          )}

          {/* Password (hidden in forgot mode) */}
          {mode !== 'forgot' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#848e9c' }}>
                {mode === 'reset' ? 'New Password' : 'Password'}
              </label>
              {mode === 'login' && (
                <button
                  type="button"
                  onClick={() => { setMode('forgot'); setError(null); setSuccessMessage(null); }}
                  style={{ background: 'none', border: 'none', color: '#f0b90b', fontSize: '12px', fontWeight: 600, cursor: 'pointer', padding: 0 }}
                >
                  Forgot password?
                </button>
              )}
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                background: '#0b0e11',
                border: '1px solid #2b313a',
                borderRadius: '6px',
                padding: '0 10px',
                height: '40px'
              }}
            >
              <Lock size={15} color="#848e9c" style={{ marginRight: '8px' }} />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#eaecef',
                  fontSize: '13px'
                }}
                required
              />
              <button
                type="button"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#848e9c',
                  cursor: 'pointer',
                  padding: 0,
                  display: 'flex',
                  alignItems: 'center'
                }}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            {(mode === 'signup' || mode === 'reset') && (
              <div style={{ fontSize: '11px', color: '#848e9c', marginTop: '6px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <span style={{ color: password.length >= 8 ? '#0ecb81' : '#848e9c' }}>• 8+ chars</span>
                <span style={{ color: /[A-Z]/.test(password) ? '#0ecb81' : '#848e9c' }}>• Uppercase</span>
                <span style={{ color: /[a-z]/.test(password) ? '#0ecb81' : '#848e9c' }}>• Lowercase</span>
                <span style={{ color: /[0-9]/.test(password) ? '#0ecb81' : '#848e9c' }}>• Number</span>
              </div>
            )}
          </div>
          )}

          {/* Confirm Password (signup & reset modes) */}
          {(mode === 'signup' || mode === 'reset') && (
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#848e9c', marginBottom: '5px' }}>
                Confirm Password
              </label>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  background: '#0b0e11',
                  border: `1px solid ${confirmPassword && confirmPassword !== password ? '#f6465d' : '#2b313a'}`,
                  borderRadius: '6px',
                  padding: '0 10px',
                  height: '40px'
                }}
              >
                <Lock size={15} color="#848e9c" style={{ marginRight: '8px' }} />
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  style={{
                    flex: 1,
                    background: 'transparent',
                    border: 'none',
                    outline: 'none',
                    color: '#eaecef',
                    fontSize: '13px'
                  }}
                  required
                />
              </div>
            </div>
          )}

          {/* 2FA TOTP Input when required */}
          {mode === 'login' && requires2FA && (
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#f0b90b', marginBottom: '5px' }}>
                2FA Authenticator Code
              </label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                className="nvx-input nvx-mono-code"
                placeholder="Enter 6-digit code"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                required
              />
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%',
              height: '42px',
              borderRadius: '6px',
              border: 'none',
              background: '#f0b90b',
              color: '#0b0e11',
              fontSize: '13.5px',
              fontWeight: 800,
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              marginTop: '6px',
              opacity: loading ? 0.7 : 1,
              transition: 'background 0.15s ease'
            }}
          >
            {loading ? (
              <span>Processing...</span>
            ) : mode === 'forgot' ? (
              <>
                <span>Send Reset Link</span>
                <ArrowRight size={15} />
              </>
            ) : mode === 'reset' ? (
              <>
                <span>Reset Password</span>
                <ShieldCheck size={15} />
              </>
            ) : mode === 'login' ? (
              <>
                <span>Sign In</span>
                <ArrowRight size={15} />
              </>
            ) : (
              <>
                <span>Create Account</span>
                <ShieldCheck size={15} />
              </>
            )}
          </button>

          {(mode === 'forgot' || mode === 'reset') && (
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null); setSuccessMessage(null); }}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#848e9c',
                fontSize: '12.5px',
                cursor: 'pointer',
                marginTop: '4px'
              }}
            >
              ← Back to Sign In
            </button>
          )}
        </form>
      </div>
    </div>
  );
};
