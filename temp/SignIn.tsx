/*
SignIn.tsx
-----------
This React component shows a sign-in/sign-up interface and handles three flows:
1) Sign In: existing users log in
2) Sign Up: new users create an account
3) Forgot/Reset Password: request a reset email and set a new password using a token

Why these choices:
- We use React state (useState) to keep track of form inputs and UI mode because state automatically re-renders on change.
- useEffect reads any resetToken in the URL so deep links from an email can directly open the reset form.
- We import a useAuth hook to keep authentication logic centralized and reusable across the app.
- We show toasts for friendly success/error feedback without blocking the UI.
- Forms call async handlers that validate inputs first (fast feedback) and then call backend APIs.
*/
import { useEffect, useMemo, useState } from 'react'; // useEffect reacts to URL reset token, useState stores form data and UI mode
import type React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'; // Visual layout components
import { Input } from './ui/input'; // Text/password inputs
import { Button } from './ui/button'; // Buttons with consistent styling
import { Label } from './ui/label'; // Accessible labels for inputs
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'; // Tabbed UI to switch between Sign In and Sign Up
import { Alert, AlertDescription } from './ui/alert'; // Inline alert messages
import { Fish, Waves, AlertCircle } from 'lucide-react'; // Icons for visual polish
import { useAuth } from '../hooks/useAuth'; // Custom hook that talks to the backend for auth
import { toast } from 'sonner'; // Non-blocking notifications
import { authAPI } from '../lib/api'; // Direct API helpers for forgot/reset flows
import TimeZoneCombobox from './TimeZoneCombobox';
import { useNavigate } from 'react-router-dom';

export function SignIn() {
  const { signIn, signUp, loading } = useAuth();
  const navigate = useNavigate();
  const [signInForm, setSignInForm] = useState({ email: '', password: '' });
  const [signUpForm, setSignUpForm] = useState({ email: '', password: '', name: '', confirmPassword: '' });
  // Time zone for signup
  const [signUpTimeZone, setSignUpTimeZone] = useState<string>(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  });
  // time zone list handled by TimeZoneCombobox
  const [error, setError] = useState<string>('');
  const [authMode, setAuthMode] = useState<'tabs' | 'forgot' | 'reset'>('tabs');
  const [forgotEmail, setForgotEmail] = useState('');
  const [resetPasswordForm, setResetPasswordForm] = useState({ password: '', confirm: '' });
  const [resetToken, setResetToken] = useState<string>('');

  const passwordPolicyMessage = 'Password must be at least 10 characters and include at least 1 special character.';
  const isStrongPassword = (pw: string) => pw.length >= 10 && /[^A-Za-z0-9]/.test(pw);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get('resetToken');
    if (t) {
      setResetToken(t);
      setAuthMode('reset');
    }
  }, []);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!signInForm.email || !signInForm.password) {
      setError('Please fill in all fields');
      return;
    }

    const result = await signIn(signInForm.email, signInForm.password);
    if (!result.success) {
      // Map backend reasons to specific UI messages
      if (result.status === 403 && (result.error?.toLowerCase?.().includes('disabled') ?? false)) {
        setError('Account disabled');
      } else if (result.status === 401) {
        setError('Invalid username or password.');
      } else {
        setError('Invalid username or password.');
      }
    } else {
      toast.success('Successfully signed in!');
      // Ensure the first page after login is always the Dashboard
      navigate('/Dashboard', { replace: true });
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!signUpForm.email || !signUpForm.password || !signUpForm.name || !signUpForm.confirmPassword || !signUpTimeZone) {
      setError('Please fill in all fields');
      return;
    }

    if (signUpForm.password !== signUpForm.confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (!isStrongPassword(signUpForm.password)) {
      setError(passwordPolicyMessage);
      return;
    }

    const success = await signUp(signUpForm.email, signUpForm.password, signUpForm.name, signUpTimeZone);
    if (!success) {
      setError('Failed to create account');
    } else {
      toast.success('Account created successfully!');
      // After successful sign-up, send user to Dashboard as the first page
      navigate('/Dashboard', { replace: true });
    }
  };

  const handleForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await authAPI.forgotPassword(forgotEmail);
      toast.success('If an account exists for that email, a reset link has been sent.');
      setAuthMode('tabs');
    } catch (e: any) {
      // API always returns success; this catch is for network errors
      toast.error('Unable to process request right now');
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!resetPasswordForm.password || !resetPasswordForm.confirm) {
      setError('Please fill in all fields');
      return;
    }
    if (resetPasswordForm.password !== resetPasswordForm.confirm) {
      setError('Passwords do not match');
      return;
    }
    if (!isStrongPassword(resetPasswordForm.password)) {
      setError(passwordPolicyMessage);
      return;
    }
    try {
      await authAPI.resetPassword(resetToken, resetPasswordForm.password);
      toast.success('Password has been reset. You can now sign in.');
      // Remove token from URL
      window.history.replaceState({}, document.title, window.location.pathname);
      setAuthMode('tabs');
    } catch (err: any) {
      setError(err?.message || 'Failed to reset password');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-cyan-50 to-blue-100 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center mb-4">
            <div className="relative">
              <Fish className="h-12 w-12 text-primary" />
              <Waves className="h-6 w-6 text-cyan-500 absolute -bottom-1 -right-1" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-foreground">ClearAquatics</h1>
          <p className="text-muted-foreground mt-2">
            Your complete aquarium management system
          </p>
        </div>

        <Card>
          <CardHeader className="text-center pb-4">
            <CardTitle>Welcome Back</CardTitle>
            <CardDescription>
              {authMode === 'tabs' ? 'Sign in to manage your aquariums and track water quality' : authMode === 'forgot' ? 'Request a password reset link' : 'Set a new password'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {authMode === 'tabs' && (
              <>
                <Tabs defaultValue="signin" className="w-full">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="signin">Sign In</TabsTrigger>
                    <TabsTrigger value="signup">Sign Up</TabsTrigger>
                  </TabsList>

                  <TabsContent value="signin" className="space-y-4">
                    <form onSubmit={handleSignIn} className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="email">Email</Label>
                        <Input
                          id="email"
                          type="email"
                          placeholder="your@email.com"
                          value={signInForm.email}
                          onChange={(e) => setSignInForm(prev => ({ ...prev, email: e.target.value }))}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="password">Password</Label>
                        <Input
                          id="password"
                          type="password"
                          placeholder="Your password"
                          value={signInForm.password}
                          onChange={(e) => setSignInForm(prev => ({ ...prev, password: e.target.value }))}
                          required
                        />
                      </div>

                      <div className="text-right">
                        <button type="button" className="text-sm text-primary underline" onClick={() => setAuthMode('forgot')}>Forgot password?</button>
                      </div>

                      {error && (
                        <Alert variant="destructive">
                          <AlertCircle className="h-4 w-4" />
                          <AlertDescription>{error}</AlertDescription>
                        </Alert>
                      )}

                      <Button type="submit" className="w-full" disabled={loading}>
                        {loading ? 'Signing in...' : 'Sign In'}
                      </Button>
                    </form>
                  </TabsContent>

                  <TabsContent value="signup" className="space-y-4">
                    <form onSubmit={handleSignUp} className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="name">Full Name</Label>
                        <Input
                          id="name"
                          type="text"
                          placeholder="Your full name"
                          value={signUpForm.name}
                          onChange={(e) => setSignUpForm(prev => ({ ...prev, name: e.target.value }))}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="signup-email">Email</Label>
                        <Input
                          id="signup-email"
                          type="email"
                          placeholder="your@email.com"
                          value={signUpForm.email}
                          onChange={(e) => setSignUpForm(prev => ({ ...prev, email: e.target.value }))}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="signup-password">Password</Label>
                        <Input
                          id="signup-password"
                          type="password"
                          placeholder="At least 10 characters with a special character"
                          value={signUpForm.password}
                          onChange={(e) => setSignUpForm(prev => ({ ...prev, password: e.target.value }))}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="confirm-password">Confirm Password</Label>
                        <Input
                          id="confirm-password"
                          type="password"
                          placeholder="Confirm your password"
                          value={signUpForm.confirmPassword}
                          onChange={(e) => setSignUpForm(prev => ({ ...prev, confirmPassword: e.target.value }))}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label id="signup-tz-label">Time Zone</Label>
                        <TimeZoneCombobox value={signUpTimeZone} onChange={setSignUpTimeZone} labeledById="signup-tz-label" />
                        <p className="text-xs text-muted-foreground">Used for timestamps and localizing your data. You can change this later in Profile.</p>
                      </div>
                      
                      {error && (
                        <Alert variant="destructive">
                          <AlertCircle className="h-4 w-4" />
                          <AlertDescription>{error}</AlertDescription>
                        </Alert>
                      )}

                      <Button type="submit" className="w-full" disabled={loading}>
                        {loading ? 'Creating Account...' : 'Create Account'}
                      </Button>
                    </form>
                  </TabsContent>
                </Tabs>
              </>
            )}

            {authMode === 'forgot' && (
              <form onSubmit={handleForgot} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="forgot-email">Email</Label>
                  <Input id="forgot-email" type="email" placeholder="your@email.com" value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} required />
                </div>
                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="ghost" onClick={() => setAuthMode('tabs')}>Cancel</Button>
                  <Button type="submit">Send Reset Link</Button>
                </div>
              </form>
            )}

            {authMode === 'reset' && (
              <form onSubmit={handleReset} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="new-password">New Password</Label>
                  <Input id="new-password" type="password" value={resetPasswordForm.password} onChange={(e) => setResetPasswordForm(prev => ({ ...prev, password: e.target.value }))} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-new-password">Confirm New Password</Label>
                  <Input id="confirm-new-password" type="password" value={resetPasswordForm.confirm} onChange={(e) => setResetPasswordForm(prev => ({ ...prev, confirm: e.target.value }))} required />
                </div>

                {error && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="ghost" onClick={() => setAuthMode('tabs')}>Cancel</Button>
                  <Button type="submit">Reset Password</Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="text-center text-sm text-muted-foreground mt-6">
          By signing up, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
}