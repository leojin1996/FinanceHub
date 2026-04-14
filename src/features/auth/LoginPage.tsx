import { type FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { LanguageSwitcher } from "../../app/layout/LanguageSwitcher";
import { useAppState } from "../../app/state/app-state";
import { BrandMark, LockIcon, MailIcon } from "../../components/AppIcons";
import { getMessages } from "../../i18n/messages";
import { login, register } from "../../services/authApi";

interface LoginLocationState {
  from?: string;
  protected?: boolean;
}

type AuthMode = "login" | "register";

export function LoginPage() {
  const { locale, session, signIn } = useAppState();
  const messages = getMessages(locale).auth;
  const location = useLocation();
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [returnToRequestedRoute, setReturnToRequestedRoute] = useState(false);

  const locationState = location.state as LoginLocationState | null;
  const redirectTo = locationState?.from ?? "/";
  const isProtectedRedirect = locationState?.protected === true;

  if (session) {
    return <Navigate replace to={returnToRequestedRoute || isProtectedRedirect ? redirectTo : "/"} />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    const normalizedEmail = email.trim();
    const normalizedPassword = password.trim();
    if (!normalizedEmail || !normalizedPassword) {
      return;
    }

    setLoading(true);
    try {
      const authFn = mode === "register" ? register : login;
      const result = await authFn(normalizedEmail, normalizedPassword);
      setReturnToRequestedRoute(true);
      signIn({ userId: result.user.id, email: result.user.email });
      navigate(redirectTo, { replace: true });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      const lower = msg.toLowerCase();
      if (mode === "register" && lower.includes("already registered")) {
        setError(messages.errorEmailRegistered);
      } else if (mode === "login" && lower.includes("invalid email or password")) {
        setError(messages.errorInvalidCredentials);
      } else if (/failed to fetch|networkerror|load failed|network request failed/i.test(msg)) {
        setError(messages.errorNetwork);
      } else if (msg.trim()) {
        setError(msg.trim());
      } else {
        setError(messages.errorGeneric);
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setMode((prev) => (prev === "login" ? "register" : "login"));
    setError("");
  };

  const isRegister = mode === "register";
  const title = isRegister ? messages.registerTitle : messages.title;
  const subtitle = isRegister ? messages.registerSubtitle : messages.subtitle;
  const primaryAction = isRegister ? messages.registerAction : messages.signInAction;
  const switchText = isRegister ? messages.switchToLogin : messages.switchToRegister;

  const highlights = [
    messages.highlightMarkets,
    messages.highlightData,
    messages.highlightInsights,
  ];

  return (
    <main className="login-page">
      <section className="login-page__panel" aria-labelledby="login-title">
        <div className="login-page__badge">
          <BrandMark className="login-page__badge-icon" />
          <span>FinanceHub</span>
        </div>
        <article className="login-card">
          <div className="login-card__header">
            <div>
              <h1 id="login-title">{title}</h1>
              <p>{subtitle}</p>
            </div>
            <LanguageSwitcher />
          </div>
          <form className="login-card__form" onSubmit={handleSubmit}>
            <label className="login-field">
              <span>{messages.emailLabel}</span>
              <span className="login-field__control">
                <MailIcon className="login-field__icon" />
                <input
                  aria-label={messages.emailLabel}
                  onChange={(event) => setEmail(event.target.value)}
                  type="email"
                  value={email}
                />
              </span>
            </label>
            <label className="login-field">
              <span>{messages.passwordLabel}</span>
              <span className="login-field__control">
                <LockIcon className="login-field__icon" />
                <input
                  aria-label={messages.passwordLabel}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  value={password}
                />
              </span>
            </label>
            {error && <p className="login-card__error">{error}</p>}
            <button className="login-card__primary-action" disabled={loading} type="submit">
              {loading ? "..." : primaryAction}
            </button>
            <button className="login-card__secondary-action" onClick={toggleMode} type="button">
              {switchText}
            </button>
          </form>
        </article>
        <section className="login-highlights">
          {highlights.map((highlight) => (
            <article className="login-highlights__card" key={highlight}>
              <p>{highlight}</p>
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}
